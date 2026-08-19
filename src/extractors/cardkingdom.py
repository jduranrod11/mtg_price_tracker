import asyncio
import httpx
import json
import os
import time
from typing import List, Dict
from src.utils.logger import get_logger

logger = get_logger(__name__)

class CardKingdomExtractor:
    def __init__(self, delay_entre_peticiones: float = 0, tasa_usd_clp: int = 800):
        # La API Oficial Pública de Card Kingdom
        self.api_url = "https://api.cardkingdom.com/api/v2/pricelist"
        self.tasa_usd_clp = tasa_usd_clp
        self.cache_file = "ck_pricelist_cache.json"
        
        # Diccionario para búsquedas ultrarrápidas en memoria
        self.ck_data_index = {}

    async def _descargar_base_datos(self):
        # 1. Comprobar si tenemos un caché reciente (menos de 12 horas)
        if os.path.exists(self.cache_file):
            antiguedad = time.time() - os.path.getmtime(self.cache_file)
            if antiguedad < (12 * 3600):
                logger.info("Cargando lista de precios de Card Kingdom desde caché local...")
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    datos = json.load(f)
                self._indexar_datos(datos)
                return

        # 2. Descargar la DB desde cero
        logger.info("Descargando base de datos completa de Card Kingdom. Esto tomará unos segundos...")
        
        # --- NUEVO: Headers hiper-realistas para evadir el WAF (Web Application Firewall) ---
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9,es;q=0.8',
            'Referer': 'https://www.cardkingdom.com/',
            'Connection': 'keep-alive'
        }
        
        async with httpx.AsyncClient(timeout=60.0, http2=True) as client:
            try:
                response = await client.get(self.api_url, headers=headers)
                response.raise_for_status()
                datos_json = response.json()
                
                # Guardamos el caché para no volver a descargar hoy
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(datos_json, f)
                    
                self._indexar_datos(datos_json)
                logger.info("Base de datos de Card Kingdom descargada e indexada con éxito.")
            except Exception as e:
                logger.error(f"Error crítico conectando a la API de Card Kingdom: {e}")

    def _indexar_datos(self, datos_json: dict):
        catalogo = datos_json.get("data", [])
        self.ck_data_index = {}
        
        # Creamos un índice agrupando todas las ediciones y variantes de una misma carta
        for item in catalogo:
            nombre = item.get("name", "").lower()
            if nombre not in self.ck_data_index:
                self.ck_data_index[nombre] = []
            self.ck_data_index[nombre].append(item)

    async def extraer_precios_batch(self, tiendas: List[str], cartas: List[str]) -> List[Dict]:
        logger.info(f"Iniciando extracción de Card Kingdom ({len(cartas)} cartas).")
        
        # Cargar los datos antes de buscar
        if not self.ck_data_index:
            await self._descargar_base_datos()
            
        resultados_totales = []
        
        for carta_nombre in cartas:
            # Limpieza para que "Ugin's Labyrinth" o "ugin's labyrinth" hagan match
            nombre_buscado = carta_nombre.lower().replace("’", "'")
            
            # Consultamos la memoria RAM (Tiempo de respuesta: ~0.001 milisegundos)
            coincidencias = self.ck_data_index.get(nombre_buscado, [])
            
            for item in coincidencias:
                precio_usd = float(item.get("price_retail", 0))
                
                # Omitimos si no tiene precio definido
                if precio_usd <= 0:
                    continue
                    
                edicion = item.get("edition", "Unknown")
                es_foil = item.get("is_foil", "false") == "true"
                acabado = "Foil" if es_foil else "No Foil"
                
                nombre_real = item.get("name", carta_nombre)
                
                # Construir Título fingiendo ser el scraping para no romper el parser
                titulo_armado = f"{nombre_real} [{edicion}] - EN NM {acabado}"
                
                resultados_totales.append({
                    'tienda_url': 'https://www.cardkingdom.com',
                    'carta_nombre': carta_nombre,
                    'titulo_tienda': titulo_armado,
                    'precio_clp': precio_usd * self.tasa_usd_clp
                })
                
        logger.info(f"Card Kingdom listo. Se procesaron {len(resultados_totales)} variantes desde la API.")
        return resultados_totales