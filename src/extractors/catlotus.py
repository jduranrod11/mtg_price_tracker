import asyncio
import httpx
import urllib.parse
import re
from typing import List, Dict
from src.extractors.base import BaseExtractor
from src.utils.logger import get_logger

logger = get_logger(__name__)

class CatLotusExtractor(BaseExtractor):
    HTTP_TIMEOUT = 30.0  # Cat Lotus pagina resultados; damos más margen que el resto de tiendas

    def __init__(self, delay_entre_peticiones: float = 2.0): # <-- Aumentamos el delay por defecto
        super().__init__(delay_entre_peticiones=delay_entre_peticiones)
        self.api_base_url = "https://catlotus.cl/api/cards"

    @staticmethod
    def _traducir_idioma(idioma_api: str) -> str:
        """Código de idioma de Cat Lotus -> la palabra que reconoce el parser.

        `parsear_atributos_carta` detecta el idioma por la palabra completa
        ("Español", "Japonés"), nunca por el código de dos letras: emitir "ES"
        hacía que todas las cartas en español de Cat Lotus quedaran guardadas
        como inglesas.
        """
        codigo = (idioma_api or "eng").lower()

        if "esp" in codigo or "spa" in codigo:
            return "Español"
        if "jpn" in codigo or "jap" in codigo:
            return "Japonés"
        if "chi" in codigo or "zho" in codigo:
            return "Chino"
        return "Inglés"

    async def _fetch_single_card(self, client: httpx.AsyncClient, tienda_url: str, carta_nombre: str) -> List[Dict]:
        termino_busqueda = re.split(r"[',\/]", carta_nombre)[0].strip()
        busqueda_limpia = urllib.parse.quote_plus(termino_busqueda)

        resultados = []
        pagina_actual = 1
        total_paginas = 1

        while pagina_actual <= total_paginas:
            url = f"{self.api_base_url}?page={pagina_actual}&perPage=100&search={busqueda_limpia}&set="

            response = await self._get_with_retry(client, url)
            if not response:
                logger.error(f"Fallo definitivo en Cat Lotus para '{carta_nombre}' (Página {pagina_actual}).")
                break

            try:
                json_response = response.json()
            except Exception as e:
                logger.error(f"Error decodificando JSON de {url}: {e}")
                break

            datos = json_response.get("data", [])
            total_paginas = json_response.get("totalPages", 1)

            if not datos:
                break

            for grupo_edicion in datos:
                nombre_db = grupo_edicion.get("name", "")

                # El buscador de Cat Lotus es por subcadena y devuelve homónimos
                # ('Dread Defiler' al buscar 'Defile'): exigimos el nombre exacto.
                if not self._nombre_coincide(carta_nombre, nombre_db):
                    logger.debug(f"Descartado por filtro estricto: '{nombre_db}' no es '{carta_nombre}'")
                    continue

                edicion = grupo_edicion.get("set_name", "Unknown Set")
                numero_coleccionista = grupo_edicion.get("collector_number", "")
                items_en_stock = grupo_edicion.get("items", [])

                for item in items_en_stock:
                    cantidad = int(item.get("quantity", 0))
                    precio = float(item.get("price_int", 0))

                    if cantidad <= 0 or precio <= 0:
                        continue

                    idioma = self._traducir_idioma(item.get("language", "eng"))

                    es_foil = bool(item.get("foil", 0))
                    acabado = "Foil" if es_foil else "No Foil"

                    estado_raw = str(item.get("state", "1"))
                    if estado_raw == "2": estado = "LP"
                    elif estado_raw in ["3", "4", "5"]: estado = "MP"
                    else: estado = "NM"

                    titulo_armado = f"{nombre_db} [{edicion}] - {idioma} {estado} {acabado}"
                    if numero_coleccionista:
                         titulo_armado += f" #{numero_coleccionista}"

                    resultados.append(
                        self._construir_resultado(tienda_url, carta_nombre, titulo_armado, precio)
                    )

            pagina_actual += 1
            if pagina_actual <= total_paginas:
                await asyncio.sleep(1.0) # Respiro mayor entre páginas

        return resultados

    async def extraer_precios_batch(self, tiendas: List[str], cartas: List[str]) -> List[Dict]:
        tienda_url = tiendas[0] if tiendas else "https://www.catlotus.cl"
        logger.info(f"Iniciando extracción API nativa Cat Lotus: {len(cartas)} cartas.")
        return await super().extraer_precios_batch([tienda_url], cartas)
