import asyncio
import httpx
import urllib.parse
import re
from typing import List, Dict
from src.utils.logger import get_logger

logger = get_logger(__name__)

class CatLotusExtractor:
    def __init__(self, delay_entre_peticiones: float = 2.0): # <-- Aumentamos el delay por defecto
        self.api_base_url = "https://catlotus.cl/api/cards"
        self.delay = delay_entre_peticiones
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }

    async def _fetch_single_card(self, client: httpx.AsyncClient, tienda_url: str, carta_nombre: str) -> List[Dict]:
        termino_busqueda = re.split(r"[',\/]", carta_nombre)[0].strip()
        busqueda_limpia = urllib.parse.quote_plus(termino_busqueda)
        
        resultados = []
        pagina_actual = 1
        total_paginas = 1
        
        carta_buscada_normalizada = carta_nombre.replace("’", "'").lower()

        while pagina_actual <= total_paginas:
            url = f"{self.api_base_url}?page={pagina_actual}&perPage=100&search={busqueda_limpia}&set="
            
            # --- NUEVO: Lógica de Reintentos (Exponential Backoff) ---
            max_reintentos = 3
            json_response = None
            
            for intento in range(max_reintentos):
                try:
                    response = await client.get(url)
                    
                    # Si el servidor nos pide que bajemos la velocidad
                    if response.status_code == 429:
                        tiempo_espera = (intento + 1) * 3  # Esperará 3s, luego 6s, luego 9s
                        logger.warning(f"[429] Cat Lotus limitó la conexión. Pausando {tiempo_espera}s antes de reintentar...")
                        await asyncio.sleep(tiempo_espera)
                        continue
                        
                    response.raise_for_status()
                    json_response = response.json()
                    break  # Salimos del bucle si la petición fue exitosa
                    
                except Exception as e:
                    if intento == max_reintentos - 1:
                        logger.error(f"Fallo definitivo en Cat Lotus para '{carta_nombre}' (Página {pagina_actual}): {e}")
                        return resultados
                    await asyncio.sleep(2)
            
            # Si se agotaron los reintentos y no obtuvimos datos, abortamos esta carta
            if not json_response:
                break
            # ---------------------------------------------------------

            datos = json_response.get("data", [])
            total_paginas = json_response.get("totalPages", 1)
            
            if not datos:
                break

            for grupo_edicion in datos:
                nombre_db = grupo_edicion.get("name", "")
                nombre_db_normalizado = nombre_db.replace("’", "'").lower()
                
                if carta_buscada_normalizada not in nombre_db_normalizado:
                    continue
                    
                edicion = grupo_edicion.get("set_name", "Unknown Set")
                numero_coleccionista = grupo_edicion.get("collector_number", "")
                items_en_stock = grupo_edicion.get("items", [])
                
                for item in items_en_stock:
                    cantidad = int(item.get("quantity", 0))
                    precio = float(item.get("price_int", 0))
                    
                    if cantidad <= 0 or precio <= 0:
                        continue
                    
                    idioma_raw = item.get("language", "eng").lower()
                    if "esp" in idioma_raw or "spa" in idioma_raw: idioma = "ES"
                    elif "jpn" in idioma_raw: idioma = "JP"
                    elif "chi" in idioma_raw or "zho" in idioma_raw: idioma = "CN"
                    else: idioma = "EN"
                    
                    es_foil = bool(item.get("foil", 0))
                    acabado = "Foil" if es_foil else "No Foil"
                    
                    estado_raw = str(item.get("state", "1"))
                    if estado_raw == "2": estado = "LP"
                    elif estado_raw in ["3", "4", "5"]: estado = "MP"
                    else: estado = "NM"

                    titulo_armado = f"{nombre_db} [{edicion}] - {idioma} {estado} {acabado}"
                    if numero_coleccionista:
                         titulo_armado += f" #{numero_coleccionista}"

                    resultados.append({
                        'tienda_url': tienda_url.rstrip('/'),
                        'carta_nombre': carta_nombre,
                        'titulo_tienda': titulo_armado,
                        'precio_clp': precio
                    })
            
            pagina_actual += 1
            if pagina_actual <= total_paginas:
                await asyncio.sleep(1.0) # Respiro mayor entre páginas
                
        return resultados

    async def extraer_precios_batch(self, tiendas: List[str], cartas: List[str]) -> List[Dict]:
        tienda_url = tiendas[0] if tiendas else "https://www.catlotus.cl"
        logger.info(f"Iniciando extracción API nativa Cat Lotus: {len(cartas)} cartas.")
        
        resultados_totales = []
        async with httpx.AsyncClient(headers=self.headers, http2=True, timeout=30.0) as client:
            for i, carta in enumerate(cartas, 1):
                logger.info(f"[catlotus.cl] Buscando ({i}/{len(cartas)}): '{carta}'")
                res = await self._fetch_single_card(client, tienda_url, carta)
                resultados_totales.extend(res)
                
                if i < len(cartas):
                    await asyncio.sleep(self.delay)
                    
        return resultados_totales