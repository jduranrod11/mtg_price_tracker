import asyncio
import httpx
import re
import unicodedata
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)

_ESPACIOS = re.compile(r"\s+")


class BaseExtractor(ABC):
    """
    Clase base abstracta para extractores de precios.

    Centraliza los reintentos con Exponential Backoff, la normalización
    de resultados y el patrón de concurrencia "tiendas en paralelo /
    cartas en serie" exigido por CLAUDE.md (Arquitectura de Extractores,
    puntos 2 y 3). Cada tienda solo debe implementar `_fetch_single_card`
    con su propia estrategia de búsqueda amplia y parseo (punto 4).
    """

    # Spoofing hiper-realista de un Chrome 124 real (CLAUDE.md #3): Cloudflare
    # compara los headers declarados contra el fingerprint del cliente, así que
    # los sec-ch-ua / sec-fetch-* deben ir completos y coherentes entre sí.
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
        'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'Connection': 'keep-alive',
    }
    RETRY_STATUS_CODES = {403, 429}
    HTTP_TIMEOUT = 25.0

    # HTTP/1.1 forzado a propósito: el handshake HTTP/2 de httpx delata el TLS
    # fingerprint del cliente Python y Cloudflare responde 403 en las tiendas
    # Shopify. Bajando a HTTP/1.1 el filtrado es mucho menos estricto.
    HTTP2 = False

    def __init__(self, delay_entre_peticiones: float = 2.0, headers: Optional[Dict] = None):
        """
        :param delay_entre_peticiones: Segundos de pausa de cortesía entre cartas de una misma tienda.
        :param headers: Headers adicionales/override sobre los DEFAULT_HEADERS de la clase.
        """
        self.delay = delay_entre_peticiones
        self.headers = {**self.DEFAULT_HEADERS, **(headers or {})}

    async def _get_with_retry(self, client: httpx.AsyncClient, url: str, max_retries: int = 3) -> Optional[httpx.Response]:
        """Realiza un GET con Exponential Backoff ante bloqueos (429/403). Ver CLAUDE.md #3."""
        for attempt in range(max_retries):
            try:
                response = await client.get(url, follow_redirects=True)

                if response.status_code in self.RETRY_STATUS_CODES:
                    wait_time = 2 ** attempt
                    logger.warning(f"Bloqueo HTTP {response.status_code} en {url}. Reintentando en {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response

            except httpx.HTTPError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Fallo definitivo consultando {url}: {e}")
        return None

    @staticmethod
    def _normalizar_nombre(texto: str) -> str:
        """Minúsculas, sin acentos y con apóstrofes/espacios unificados.

        Permite que 'Lim-Dul's Vault' calce con "Lim-Dûl’s Vault".
        """
        texto = texto.replace("’", "'").replace("`", "'")
        texto = unicodedata.normalize("NFKD", texto)
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        return _ESPACIOS.sub(" ", texto).strip().lower()

    @classmethod
    def _nombre_coincide(cls, carta_nombre: str, nombre_tienda: str) -> bool:
        """Filtro estricto local para APIs que exponen el nombre de carta limpio.

        Complementa la Búsqueda Amplia (CLAUDE.md #4): la consulta a la API va
        con la raíz del nombre, y acá se exige igualdad EXACTA, nunca subcadena.
        Así 'Defile' deja de calzar con 'Dread Defiler' o 'Defiler of Flesh'.

        Para cartas dobles/split la tienda guarda "Cara A // Cara B", así que
        cualquiera de las dos caras valida la carta buscada.
        """
        carta = cls._normalizar_nombre(carta_nombre)
        nombre = cls._normalizar_nombre(nombre_tienda)

        if not carta or not nombre:
            return False

        if carta == nombre:
            return True

        return "//" in nombre and carta in [cara.strip() for cara in nombre.split("//")]

    @staticmethod
    def _normalizar_precio_clp(precio_raw, unidad_menor: int = 2) -> float:
        """Convierte un precio expresado en unidades menores a CLP reales.

        `unidad_menor` es cuántos decimales usa la API, y cada tienda lo declara:
        WooCommerce lo publica en `prices.currency_minor_unit` (0 para CLP) y la
        API `.js` de Shopify siempre entrega centésimas ($39.500 -> 3950000).

        NO se infiere del valor. La heurística anterior ("divide por 100 si es
        mayor a 1.000 y múltiplo de 100") convertía un precio real de $25.000 en
        $250 y uno de $1.500 en $15 apenas una tienda cotizara en cifras redondas.
        """
        return float(precio_raw) / (10 ** unidad_menor)

    @staticmethod
    def _construir_resultado(tienda_url: str, carta_nombre: str, titulo_tienda: str, precio_clp: float) -> Dict:
        return {
            'tienda_url': tienda_url.rstrip('/'),
            'carta_nombre': carta_nombre,
            'titulo_tienda': titulo_tienda,
            'precio_clp': precio_clp,
        }

    @abstractmethod
    async def _fetch_single_card(self, client: httpx.AsyncClient, tienda_url: str, carta_nombre: str) -> List[Dict]:
        """Busca una carta en una tienda puntual. Cada extractor implementa su propia
        Búsqueda Amplia + filtro estricto local (CLAUDE.md #4)."""
        raise NotImplementedError

    async def _procesar_tienda(self, client: httpx.AsyncClient, tienda: str, cartas: List[str]) -> List[Dict]:
        """Procesa todas las cartas de UNA SOLA tienda de forma secuencial."""
        resultados_tienda = []
        total_cartas = len(cartas)
        tienda_nombre = tienda.replace("https://", "").replace("www.", "").rstrip('/')

        for i, carta in enumerate(cartas, 1):
            logger.info(f"[{tienda_nombre}] Buscando ({i}/{total_cartas}): '{carta}'")
            res = await self._fetch_single_card(client, tienda, carta)
            resultados_tienda.extend(res)

            if i < total_cartas:
                await asyncio.sleep(self.delay)

        return resultados_tienda

    async def extraer_precios_batch(self, tiendas: List[str], cartas: List[str]) -> List[Dict]:
        """Template method: tiendas concurrentes, cartas en serie dentro de cada tienda."""
        logger.info(f"Iniciando extracción asíncrona {self.__class__.__name__}: {len(cartas)} cartas en {len(tiendas)} tiendas.")

        async with httpx.AsyncClient(headers=self.headers, http2=self.HTTP2, timeout=self.HTTP_TIMEOUT) as client:
            tareas = [self._procesar_tienda(client, tienda, cartas) for tienda in tiendas]
            resultados_brutos = await asyncio.gather(*tareas)
            return [item for sublist in resultados_brutos for item in sublist]
