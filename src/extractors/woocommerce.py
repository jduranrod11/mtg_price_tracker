import html
import httpx
import re
import urllib.parse
from typing import List, Dict
from src.extractors.base import BaseExtractor
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Separadores con los que algunas tiendas anexan condición/idioma al nombre del
# producto: "Sol Ring — Near Mint · Spanish" (rhysticbazaar.cl). Se exige espacio
# a ambos lados para no tocar nombres con guion ("Lim-Dûl's Vault") ni cartas
# dobles ("Fire // Ice").
_SUFIJO_ATRIBUTOS = re.compile(r"\s+[—–·|]\s+")

class WooCommerceExtractor(BaseExtractor):
    def __init__(self, delay_entre_peticiones: float = 2.0):
        super().__init__(
            delay_entre_peticiones=delay_entre_peticiones,
            headers={
                'Accept-Language': 'es-CL,es;q=0.9,en;q=0.8',
                'Upgrade-Insecure-Requests': '1',
            },
        )

    @staticmethod
    def _limpiar_nombre(nombre_producto: str) -> str:
        """Recorta los atributos que algunas tiendas anexan al nombre del producto.

        rhysticbazaar.cl publica "Sol Ring — Near Mint · Spanish"; la condición y el
        idioma vienen además en `attributes`, así que acá solo nos interesa quedarnos
        con el nombre de la carta para poder compararlo de forma exacta.
        cardnexus.cl y el resto, que ya publican el nombre limpio, quedan intactos.
        """
        return _SUFIJO_ATRIBUTOS.split(nombre_producto, maxsplit=1)[0].strip()

    async def _fetch_single_card(self, client: httpx.AsyncClient, tienda_url: str, carta_nombre: str) -> List[Dict]:
        busqueda_limpia = carta_nombre.split("'")[0] if "'" in carta_nombre else carta_nombre
        query = urllib.parse.quote(busqueda_limpia)

        # Aumentamos el per_page a 100 para que no corte las variantes en cartas con muchos homónimos
        api_url = f"{tienda_url.rstrip('/')}/wp-json/wc/store/products?search={query}&per_page=100"

        resultados = []
        response = await self._get_with_retry(client, api_url)

        if not response or response.status_code != 200:
            return resultados

        try:
            productos = response.json()
        except Exception as e:
            logger.error(f"Error decodificando JSON de {api_url}: {e}")
            return resultados

        for prod in productos:
            # WooCommerce devuelve el nombre con entidades HTML ("Inventors&#8217; Fair",
            # "R&amp;D's Secret Lair"); html.unescape cubre todas, no solo dos casos.
            nombre_producto = self._limpiar_nombre(html.unescape(prod.get('name', '')))

            # El buscador de WooCommerce responde por subcadena y trae homónimos
            # ('Defiler of Flesh' al buscar 'Defile'): exigimos el nombre exacto.
            if not self._nombre_coincide(carta_nombre, nombre_producto):
                logger.debug(f"Descartado por filtro estricto: '{nombre_producto}' no es '{carta_nombre}'")
                continue

            if not prod.get('is_purchasable', False) or not prod.get('is_in_stock', False):
                continue

            # La Store API declara la escala del precio: en CLP `currency_minor_unit`
            # es 0, así que 2690 son $2.690 y no $26,90.
            precios = prod.get('prices', {})
            try:
                precio_clp = self._normalizar_precio_clp(
                    precios.get('price', '0'), int(precios.get('currency_minor_unit', 0))
                )
            except (ValueError, TypeError):
                continue

            if precio_clp <= 0:
                continue

            # Separar Edición de otros atributos para estructurar el nombre
            edicion_api = ""
            otros_atributos = []

            for attr in prod.get('attributes', []):
                nombre_attr = attr.get('name', '').lower()
                for term in attr.get('terms', []):
                    term_name = term.get('name', '')
                    # Detectar si el atributo corresponde a la expansión/edición
                    if 'edición' in nombre_attr or 'edicion' in nombre_attr or 'set' in nombre_attr:
                        edicion_api = term_name
                    else:
                        otros_atributos.append(term_name)

            # Formatear: "NombreCarta [Edición] - Atributos Extra"
            titulo_tienda = nombre_producto
            if edicion_api:
                titulo_tienda += f" [{edicion_api}]"
            if otros_atributos:
                titulo_tienda += f" - {' '.join(otros_atributos)}"

            resultados.append(
                self._construir_resultado(tienda_url, carta_nombre, titulo_tienda, precio_clp)
            )

        return resultados
