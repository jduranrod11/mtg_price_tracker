import asyncio
import httpx
import re
import urllib.parse
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from src.extractors.base import BaseExtractor
from src.utils.logger import get_logger

logger = get_logger(__name__)

# El alt de la imagen trae nombre, expansión y acabado: "Reprieve (HOC) Foil".
_ALT_PRODUCTO = re.compile(r"^(?P<nombre>.+?)\s*\((?P<edicion>[A-Z0-9]{2,6})\)\s*(?P<foil>Foil)?\s*$")

# El badge de cada tarjeta: "EN · NM", o "EN +1 · NM" cuando hay más idiomas.
_BADGE = re.compile(r"^\s*(?P<idioma>[A-Z]{2})(?:\s*\+\d+)?\s*·\s*(?P<estado>[A-Z]{2})\s*$")

_PRECIO = re.compile(r"^\s*\$[\d.]+")

# El parser del pipeline reconoce el idioma por la palabra, nunca por el código.
_IDIOMAS = {"EN": "Inglés", "ES": "Español", "JP": "Japonés", "PT": "Portugués", "IT": "Italiano",
            "FR": "Francés", "DE": "Alemán", "RU": "Ruso", "KO": "Coreano", "CN": "Chino"}

# Escala de condición de la tienda -> la del proyecto (ver `src/utils/parsers.py`).
_ESTADOS = {"NM": "NM", "EX": "LP", "LP": "LP", "SP": "LP", "VG": "MP", "GD": "MP",
            "MP": "MP", "HP": "HP", "PL": "HP", "DM": "DM", "PO": "DM"}


class CartasMagicsurExtractor(BaseExtractor):
    """
    Extractor para cartasmagicsur.cl (Next.js sobre Vercel, backend Supabase).

    La ficha `/carta/{set}-{n}-{slug}` no sirve: renderiza en el servidor solo las
    recomendaciones del pie, y el precio del producto principal lo pide el navegador
    después. Los precios sí viven en el Supabase de la tienda, pero su `robots.txt`
    declara `Disallow: /api/` y el cliente nunca consulta las cartas desde ahí, así
    que llegar a esa vía exigiría enumerar su esquema: fuera de lo que hace este
    proyecto.

    Lo que sí es público, permitido y server-side es el listado `/catalogo?q=`, que
    filtra por subcadena sobre el nombre de la carta y solo lista lo que hay en
    stock, con precio, expansión, idioma y condición en cada tarjeta.

    Ojo con el atajo que no funciona: recorrer `/catalogo?page=N` sin `q` parece
    traer el catálogo completo (termina cerca de la página 101), pero está truncado
    y omite cartas que sí tienen stock — `Solemn Simulacrum (TSR)`, `Skullclamp (FIC)`
    y `Feign Death (AFR)` aparecen en el buscador y no en ese recorrido. Hay que
    consultar carta por carta.
    """

    PRODUCTOS_POR_PAGINA = 12
    MAX_PAGINAS = 10  # ~120 resultados por carta; los nombres raíz cortos paginan

    def __init__(self, delay_entre_peticiones: float = 2.0):
        super().__init__(
            delay_entre_peticiones=delay_entre_peticiones,
            headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'same-origin',
                'Upgrade-Insecure-Requests': '1',
            },
        )

    # ---------- Parseo del listado ----------

    @staticmethod
    def _parsear_precio(texto: str) -> Optional[float]:
        """"$2.170" -> 2170.0. En CLP el punto separa miles, no decimales."""
        digitos = re.sub(r"[^\d]", "", texto or "")
        return float(digitos) if digitos else None

    @classmethod
    def _extraer_productos(cls, html: str) -> List[Dict]:
        """Convierte las tarjetas del listado en productos planos."""
        sopa = BeautifulSoup(html, "html.parser")
        productos = []

        for tarjeta in sopa.select('a[href^="/carta/"]'):
            imagen = tarjeta.select_one("img")
            if not imagen:
                continue

            match_alt = _ALT_PRODUCTO.match(imagen.get("alt", "") or "")
            if not match_alt:
                continue

            precio_texto = tarjeta.find(string=_PRECIO)
            if not precio_texto:
                continue  # Sin precio publicado: no hay nada que comparar

            idioma, estado = "Inglés", "NM"
            for span in tarjeta.select("span"):
                match_badge = _BADGE.match(span.get_text(strip=True))
                if match_badge:
                    idioma = _IDIOMAS.get(match_badge.group("idioma"), "Inglés")
                    estado = _ESTADOS.get(match_badge.group("estado"), "NM")
                    break

            productos.append({
                "nombre": match_alt.group("nombre").strip(),
                "edicion": match_alt.group("edicion"),
                "acabado": "Foil" if match_alt.group("foil") else "No Foil",
                "idioma": idioma,
                "estado": estado,
                "precio": cls._parsear_precio(precio_texto),
            })

        return productos

    @staticmethod
    def _armar_titulo(producto: Dict) -> str:
        """Formato canónico que consume `parsear_atributos_carta`."""
        return (
            f"{producto['nombre']} [{producto['edicion']}] - "
            f"{producto['idioma']} {producto['estado']} {producto['acabado']}"
        )

    # ---------- Extracción ----------

    async def _fetch_single_card(self, client: httpx.AsyncClient, tienda_url: str, carta_nombre: str) -> List[Dict]:
        # Búsqueda Amplia (CLAUDE.md #6): el buscador filtra por subcadena sobre el
        # nombre, así que la raíz evita que la coma o el apóstrofe lo hagan fallar.
        raiz = re.split(r"[',\/]", carta_nombre)[0].strip() or carta_nombre
        base = tienda_url.rstrip('/')
        resultados: List[Dict] = []

        for pagina in range(1, self.MAX_PAGINAS + 1):
            if pagina > 1:
                await asyncio.sleep(self.delay)  # Pausa de cortesía entre páginas

            url = f"{base}/catalogo?q={urllib.parse.quote(raiz)}&page={pagina}"
            response = await self._get_with_retry(client, url)
            if not response:
                break

            productos = self._extraer_productos(response.text)
            if not productos:
                break

            for producto in productos:
                # Filtro estricto local: igualdad exacta contra el nombre de la carta.
                if not self._nombre_coincide(carta_nombre, producto['nombre']):
                    logger.debug(f"Descartado por filtro estricto: '{producto['nombre']}' no es '{carta_nombre}'")
                    continue

                if not producto['precio'] or producto['precio'] <= 0:
                    continue

                resultados.append(
                    self._construir_resultado(
                        tienda_url, carta_nombre, self._armar_titulo(producto), producto['precio']
                    )
                )

            # El listado no viene ordenado por relevancia, así que se recorren todas
            # las páginas de la raíz: cortar antes se comería impresiones válidas.
            if len(productos) < self.PRODUCTOS_POR_PAGINA:
                break
        else:
            logger.warning(
                f"'{raiz}' alcanzó el tope de {self.MAX_PAGINAS} páginas en {base}: "
                f"puede haber impresiones sin revisar."
            )

        return resultados
