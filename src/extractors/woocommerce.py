import asyncio
import httpx
import urllib.parse
from typing import List, Dict
from src.utils.logger import get_logger

logger = get_logger(__name__)

class WooCommerceExtractor:
    def __init__(self, delay_entre_peticiones: float = 2.0):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'es-CL,es;q=0.9,en;q=0.8',
            'Upgrade-Insecure-Requests': '1'
        }
        self.delay = delay_entre_peticiones

    async def _get_with_retry(self, client: httpx.AsyncClient, url: str, max_retries: int = 3):
        for attempt in range(max_retries):
            try:
                response = await client.get(url, follow_redirects=True)
                if response.status_code in [403, 429]:
                    wait_time = 2 ** attempt
                    logger.warning(f"Bloqueo HTTP {response.status_code} en {url}. Reintentando en {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Fallo definitivo en la consulta a la API WooCommerce {url}: {e}")
        return None

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
            nombre_producto = prod.get('name', '').replace('&#8217;', "'").replace('&amp;', '&')
            
            if carta_nombre.lower() not in nombre_producto.lower():
                continue

            if not prod.get('is_purchasable', False) or not prod.get('is_in_stock', False):
                continue
            
            precio_raw = prod.get('prices', {}).get('price', '0')
            try:
                precio_clp = float(precio_raw) / 100 if float(precio_raw) > 1000 and float(precio_raw) % 100 == 0 else float(precio_raw)
            except ValueError:
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

            resultados.append({
                'tienda_url': tienda_url.rstrip('/'),
                'carta_nombre': carta_nombre,
                'titulo_tienda': titulo_tienda,
                'precio_clp': precio_clp
            })
                
        return resultados

    async def _procesar_tienda(self, client: httpx.AsyncClient, tienda: str, cartas: List[str]) -> List[Dict]:
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
        logger.info(f"Iniciando extracción asíncrona WooCommerce: {len(cartas)} cartas en {len(tiendas)} tiendas.")
        async with httpx.AsyncClient(headers=self.headers, http2=True, timeout=25.0) as client:
            tareas = [self._procesar_tienda(client, tienda, cartas) for tienda in tiendas]
            resultados_brutos = await asyncio.gather(*tareas)
            return [item for sublist in resultados_brutos for item in sublist]