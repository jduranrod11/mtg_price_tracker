import asyncio
import httpx
import re
import unicodedata
import urllib.parse
from typing import List, Dict
from src.extractors.base import BaseExtractor
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Separadores con los que las tiendas Shopify anexan edición, código de set,
# tratamiento o acabado al nombre real de la carta. Ejemplos reales:
#   "Ulamog, the Defiler (Borderless) (MH3-383) - Modern Horizons 3 Foil"
#   "Defiler of Flesh (Promo Pack) [Dominaria United Promos]"
_SEPARADORES_TITULO = re.compile(r"[()\[\]{}|]|\s[-–—:]\s|\s#")

# Palabras de acabado/tratamiento que algunas tiendas pegan al final del nombre
# sin separador ("Defile Foil"). Se recortan solo si van al final del segmento.
_SUFIJO_ADORNOS = re.compile(
    r"(?:\s*\b(?:non\s*-?\s*foil|foil|etched|borderless|showcase|retro|promo|"
    r"prerelease|surge|extended\s+art|full\s+art|alternate\s+art))+$"
)

_ESPACIOS = re.compile(r"\s+")


class ShopifyExtractor(BaseExtractor):
    def __init__(self, delay_entre_peticiones: float = 1.5):
        """
        :param delay_entre_peticiones: Segundos a esperar entre consultas a la misma tienda.
        """
        super().__init__(delay_entre_peticiones=delay_entre_peticiones)

    @staticmethod
    def _normalizar(texto: str) -> str:
        """Minúsculas, sin acentos y con apóstrofes/espacios unificados.

        Permite que 'Lim-Dul's Vault' calce con "Lim-Dûl’s Vault".
        """
        texto = texto.replace("’", "'").replace("`", "'")
        texto = unicodedata.normalize("NFKD", texto)
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        return _ESPACIOS.sub(" ", texto).strip().lower()

    @classmethod
    def _nombres_candidatos(cls, titulo: str) -> List[str]:
        """Extrae el nombre de carta que declara el título, ya normalizado.

        El nombre siempre ocupa el primer segmento (lo que va antes del primer
        paréntesis/corchete de tratamiento o edición); los segmentos posteriores
        se ignoran a propósito, porque hay ediciones que se llaman igual que una
        carta ("Fire // Ice [Apocalypse]" no debe validar la carta 'Apocalypse').

        "Defiled Crypt // Cadaver Lab (DSK-091) - Duskmourn: House of Horror Foil"
        -> ['defiled crypt // cadaver lab', 'defiled crypt', 'cadaver lab']
        """
        for bruto in _SEPARADORES_TITULO.split(titulo):
            nombre = _SUFIJO_ADORNOS.sub("", cls._normalizar(bruto)).strip()
            if not nombre:
                continue  # Segmento vacío o puro acabado ("(Foil)")

            candidatos = [nombre]

            # Cartas dobles/split ("Fire // Ice"): cada cara es un nombre válido.
            if "//" in nombre:
                candidatos.extend(cara.strip() for cara in nombre.split("//") if cara.strip())

            return candidatos

        return []

    @classmethod
    def _titulo_coincide(cls, carta_nombre: str, titulo: str) -> bool:
        """Filtro estricto local de la Búsqueda Amplia (CLAUDE.md #4).

        La API se consulta con la raíz del nombre (búsqueda amplia), así que el
        título devuelto debe validarse aquí de forma exacta: el nombre buscado
        tiene que ser EXACTAMENTE el nombre que declara el título (lo que va
        antes de los paréntesis/corchetes de la edición), no una subcadena.

        Así 'Defile' calza con "Defile [Dark Ascension]" pero se rechazan
        'Defiler of Flesh', 'Depth Defiler' y 'Ulamog, the Defiler'.
        """
        if not carta_nombre or not titulo:
            return False

        carta = cls._normalizar(carta_nombre)
        if not carta:
            return False

        return carta in cls._nombres_candidatos(titulo)

    async def _fetch_single_card(self, client: httpx.AsyncClient, tienda_url: str, carta_nombre: str) -> List[Dict]:
        """Busca el identificador de la carta y luego extrae sus variantes exactas."""
        query = urllib.parse.quote(carta_nombre)
        search_url = f"{tienda_url.rstrip('/')}/search/suggest.json?q={query}&resources[type]=product"

        resultados = []

        # 1. Obtener los identificadores (handles)
        response = await self._get_with_retry(client, search_url)
        if not response:
            return resultados

        data = response.json()
        products = data.get('resources', {}).get('results', {}).get('products', [])
        handles = [p.get('handle') for p in products if p.get('handle')]

        # 2. Consultar el JSON detallado de cada producto encontrado
        for handle in handles:
            await asyncio.sleep(self.delay)  # Pausa de cortesía para la API

            prod_url = f"{tienda_url.rstrip('/')}/products/{handle}.js"
            prod_response = await self._get_with_retry(client, prod_url)

            if not prod_response:
                continue

            prod_data = prod_response.json()
            titulo_base = prod_data.get('title', '')

            # Filtro estricto: descarta homónimos parciales ('Defiler of Flesh' para 'Defile')
            if not self._titulo_coincide(carta_nombre, titulo_base):
                logger.debug(f"Descartado por filtro estricto: '{titulo_base}' no es '{carta_nombre}'")
                continue

            variantes = prod_data.get('variants', [])

            # 3. Iterar sobre las versiones de la carta (NM, Foil, Español, etc.)
            for variant in variantes:
                # Omitir lo que no tiene stock
                if not variant.get('available', False):
                    continue

                titulo_variante = variant.get('title', '')
                if titulo_variante and titulo_variante.lower() != 'default title':
                    titulo_completo = f"{titulo_base} - {titulo_variante}"
                else:
                    titulo_completo = titulo_base

                # Shopify API (.js) nativamente devuelve los precios multiplicados por 100
                # Ej: 39500 pesos los devuelve como 3950000. Siempre, sin excepción.
                precio_clp = self._normalizar_precio_clp(variant.get('price', 0), unidad_menor=2)

                resultados.append(
                    self._construir_resultado(tienda_url, carta_nombre, titulo_completo, precio_clp)
                )

        return resultados
