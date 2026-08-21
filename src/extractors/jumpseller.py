import asyncio
import httpx
import re
import urllib.parse
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from src.extractors.base import BaseExtractor
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Jumpseller no expone una API JSON pública de storefront: `/api/products` exige
# credenciales de administrador (403) y no existe `/products.json`. La búsqueda
# `/search?q=` sí devuelve el catálogo renderizado, con nombre, precio, SKU y
# estado de stock en cada bloque de producto, así que esa es la fuente.
_PRECIO = re.compile(r"\d[\d.]*")

# SKU de magic4ever: "M-C19-0221" -> edición C19. gamequest trae la edición en el
# propio título, así que este patrón solo aplica cuando el título no la declara.
# El número admite sufijos de tratamiento: "M-40K-0249★", "M-STX-0246PP" (promo
# pack), "M-DTK-0001TL" (The List), "M-BFZ-0087PR" (prerelease).
_SKU_EDICION = re.compile(r"^[A-Z]+-([A-Z0-9]{2,6})-\d+\S*$", re.IGNORECASE)

_SEPARADOR_ATRIBUTOS = re.compile(r"\s*\|\s*")
_TRATAMIENTO = re.compile(r"\s*\(([^)]*)\)\s*$")

# Las tiendas escriben el idioma en español; `parsear_atributos_carta` lo detecta
# por la palabra completa, nunca por el código de dos letras.
_IDIOMAS = {
    "ingles": "Inglés", "inglés": "Inglés", "english": "Inglés", "en": "Inglés",
    "espanol": "Español", "español": "Español", "spanish": "Español", "es": "Español",
    "japones": "Japonés", "japonés": "Japonés", "japanese": "Japonés", "jp": "Japonés",
    "chino": "Chinese", "chinese": "Chinese",
}

# Escala de condición de las tiendas -> los códigos que usa `src/utils/parsers.py`.
# EX (Excellent) equivale a LP y VG (Very Good) a MP en la nomenclatura del proyecto.
_ESTADOS = {
    "m": "NM", "nm": "NM", "mint": "NM", "near mint": "NM",
    "ex": "LP", "sp": "LP", "lp": "LP", "excellent": "LP", "lightly played": "LP",
    "vg": "MP", "gd": "MP", "mp": "MP", "good": "MP", "moderately played": "MP",
    "pl": "HP", "hp": "HP", "heavily played": "HP", "poor": "DM", "po": "DM", "dm": "DM",
}

_SIN_STOCK = ("agotado", "sin stock", "no disponible")


class JumpsellerExtractor(BaseExtractor):
    """
    Extractor para tiendas Jumpseller (magic4ever.cl, gamequest.cl).

    A diferencia de Shopify o WooCommerce, acá no hay JSON: se parsea el HTML de
    `/search?q=`. Sigue siendo asíncrono con httpx (CLAUDE.md #3) — nada de
    navegadores headless.

    El buscador de Jumpseller hace OR entre las palabras de la consulta, así que
    "Sol Ring" devuelve 120+ páginas de cualquier cosa con "sol" o "ring". Los
    resultados vienen ordenados por relevancia y las coincidencias exactas se
    agrupan al principio, de modo que paginamos mientras la página siga trayendo
    coincidencias y cortamos apenas una no aporte ninguna.
    """

    RESULTADOS_POR_PAGINA = 40
    MAX_PAGINAS = 4

    def __init__(self, delay_entre_peticiones: float = 2.0):
        super().__init__(
            delay_entre_peticiones=delay_entre_peticiones,
            # Pedimos HTML, no JSON: los sec-fetch-* deben describir una navegación
            # real o la firma queda incoherente con el User-Agent (CLAUDE.md #4).
            headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'same-origin',
                'Upgrade-Insecure-Requests': '1',
            },
        )

    # ---------- Parseo del HTML ----------

    @staticmethod
    def _parsear_precio(texto: str) -> Optional[float]:
        """"$2.000" -> 2000.0. En CLP el punto es separador de miles, no decimal.

        No se usa `_normalizar_precio_clp`: Jumpseller publica el precio ya
        formateado en pesos, y la heurística de centésimas lo dividiría por 100.
        """
        match = _PRECIO.search(texto or "")
        if not match:
            return None
        try:
            return float(match.group(0).replace(".", ""))
        except ValueError:
            return None

    @classmethod
    def _extraer_bloques(cls, html: str) -> List[Dict]:
        """Convierte cada bloque de producto del listado en un dict plano."""
        sopa = BeautifulSoup(html, "html.parser")
        bloques = []

        for articulo in sopa.select("article"):
            nombre_el = articulo.select_one(".product-block__name")
            if not nombre_el:
                continue

            # Con variantes, el bloque muestra "desde $450 / hasta $550": nos
            # quedamos con el primer precio real (el mínimo), que es el que
            # alimenta la comparación de mejor precio local.
            precios = [
                p.get_text(strip=True)
                for p in articulo.select(".product-block__price")
                if "product-block__price--text" not in (p.get("class") or [])
            ]
            estado_el = articulo.select_one(".product-block__label--status")
            sku_el = articulo.select_one(".product-block__sku")

            bloques.append({
                "titulo": nombre_el.get_text(strip=True),
                "precio": cls._parsear_precio(precios[0]) if precios else None,
                "sku": sku_el.get_text(strip=True) if sku_el else "",
                "etiqueta_estado": estado_el.get_text(strip=True) if estado_el else "",
            })

        return bloques

    @classmethod
    def _descomponer_titulo(cls, titulo: str, sku: str) -> Dict[str, str]:
        """Separa el título de la tienda en los campos que espera el pipeline.

        gamequest: "Sol Ring (Borderless foil) | Inglés | NM | PIP"
        magic4ever: "Sol Ring" + SKU "M-C19-0221"
        """
        segmentos = [s.strip() for s in _SEPARADOR_ATRIBUTOS.split(titulo) if s.strip()]
        nombre_bruto = segmentos[0] if segmentos else titulo.strip()

        idioma, estado, edicion = "Inglés", "NM", ""
        for segmento in segmentos[1:]:
            clave = segmento.lower()
            if clave in _IDIOMAS:
                idioma = _IDIOMAS[clave]
            elif clave in _ESTADOS:
                estado = _ESTADOS[clave]
            elif not edicion:
                edicion = segmento  # El código de expansión ("PIP", "40K")

        if not edicion:
            match_sku = _SKU_EDICION.match(sku or "")
            if match_sku:
                edicion = match_sku.group(1).upper()

        # El tratamiento va entre paréntesis al final del nombre y no forma parte
        # de él: "Sol Ring (Borderless foil)" es igualmente la carta "Sol Ring".
        tratamiento = ""
        match_tratamiento = _TRATAMIENTO.search(nombre_bruto)
        if match_tratamiento:
            tratamiento = match_tratamiento.group(1).strip()
            nombre_bruto = nombre_bruto[:match_tratamiento.start()].strip()

        contexto = f"{tratamiento} {titulo}".lower()
        es_foil = "foil" in contexto and not re.search(r"non[\s-]*foil|no foil", contexto)

        # "Borderless foil" -> "Borderless": el acabado se informa aparte.
        variante = re.sub(r"\bnon[\s-]*foil\b|\bfoil\b", "", tratamiento, flags=re.IGNORECASE).strip()

        return {
            "nombre": nombre_bruto,
            "idioma": idioma,
            "estado": estado,
            "edicion": edicion,
            "acabado": "Foil" if es_foil else "No Foil",
            "variante": variante,
        }

    @staticmethod
    def _armar_titulo(info: Dict[str, str]) -> str:
        """Título en el formato canónico que consume `parsear_atributos_carta`."""
        titulo = f"{info['nombre']} [{info['edicion']}]" if info['edicion'] else info['nombre']
        titulo += f" - {info['idioma']} {info['estado']} {info['acabado']}"
        if info['variante']:
            titulo += f" {info['variante']}"
        return titulo

    # ---------- Extracción ----------

    async def _fetch_single_card(self, client: httpx.AsyncClient, tienda_url: str, carta_nombre: str) -> List[Dict]:
        # Búsqueda Amplia (CLAUDE.md #6): la raíz del nombre evita que el apóstrofe
        # o la coma rompan el buscador interno.
        raiz = re.split(r"[',\/]", carta_nombre)[0].strip() or carta_nombre
        base = tienda_url.rstrip('/')
        resultados: List[Dict] = []

        for pagina in range(1, self.MAX_PAGINAS + 1):
            url = f"{base}/search?q={urllib.parse.quote(raiz)}&page={pagina}"

            if pagina > 1:
                await asyncio.sleep(self.delay)  # Pausa de cortesía entre páginas

            response = await self._get_with_retry(client, url)
            if not response:
                break

            bloques = self._extraer_bloques(response.text)
            if not bloques:
                break

            coincidencias = 0
            for bloque in bloques:
                info = self._descomponer_titulo(bloque['titulo'], bloque['sku'])

                # Filtro estricto local: igualdad exacta contra el nombre de la carta.
                if not self._nombre_coincide(carta_nombre, info['nombre']):
                    continue

                coincidencias += 1

                if any(marca in bloque['etiqueta_estado'].lower() for marca in _SIN_STOCK):
                    continue

                if not bloque['precio'] or bloque['precio'] <= 0:
                    logger.debug(f"Sin precio publicado: '{bloque['titulo']}' en {base}")
                    continue

                resultados.append(
                    self._construir_resultado(tienda_url, carta_nombre, self._armar_titulo(info), bloque['precio'])
                )

            # Los resultados vienen por relevancia: si una página completa no trae
            # ninguna coincidencia, las siguientes tampoco lo harán.
            if coincidencias == 0:
                break

            if len(bloques) < self.RESULTADOS_POR_PAGINA:
                break  # Última página del listado

        return resultados
