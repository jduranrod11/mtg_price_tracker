import asyncio
import httpx
import urllib.parse
from typing import List, Dict
from src.utils.logger import get_logger

logger = get_logger(__name__)

class ShopifyExtractor:
    def __init__(self, delay_entre_peticiones: float = 1.5):
        """
        :param delay_entre_peticiones: Segundos a esperar entre consultas a la misma tienda.
        """
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        self.delay = delay_entre_peticiones

    async def _get_with_retry(self, client: httpx.AsyncClient, url: str, max_retries: int = 3):
        """Realiza una petición GET con reintentos automáticos si hay bloqueo (429)."""
        for attempt in range(max_retries):
            try:
                response = await client.get(url)
                
                # Si la tienda nos bloquea temporalmente por velocidad
                if response.status_code == 429:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s...
                    logger.warning(f"Rate limit (429) en {url}. Esperando {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                    
                response.raise_for_status()
                return response
                
            except httpx.HTTPError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Fallo definitivo conectando a {url}: {e}")
        return None

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
            
            if carta_nombre.lower() not in titulo_base.lower():
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
                # Ej: 39500 pesos los devuelve como 3950000.
                precio_raw = float(variant.get('price', 0))
                precio_clp = precio_raw / 100 if precio_raw > 1000 and precio_raw % 100 == 0 else precio_raw
                    
                resultados.append({
                    'tienda_url': tienda_url.rstrip('/'),
                    'carta_nombre': carta_nombre,
                    'titulo_tienda': titulo_completo,
                    'precio_clp': precio_clp
                })
                
        return resultados

    async def _fetch_single_card_with_semaphore(self, semaphore: asyncio.Semaphore, client: httpx.AsyncClient, tienda_url: str, carta_nombre: str, i: int, total: int, tienda_nombre: str) -> List[Dict]:
        """Envuelve la petición de la carta con un semáforo para limitar concurrencia."""
        async with semaphore:
            logger.info(f"[{tienda_nombre}] Buscando ({i}/{total}): '{carta_nombre}'")
            # Añadimos un pequeño sleep base si tienes un delay configurado para evitar ráfagas instantáneas
            if self.delay > 0:
                await asyncio.sleep(self.delay)
            return await self._fetch_single_card(client, tienda_url, carta_nombre)

    async def _procesar_tienda(self, client: httpx.AsyncClient, tienda: str, cartas: List[str]) -> List[Dict]:
        """Procesa las cartas de una tienda CONCURRENTEMENTE usando un semáforo."""
        total_cartas = len(cartas)
        tienda_nombre = tienda.replace("https://", "").replace("www.", "").rstrip('/')
        
        # Límite estricto de peticiones simultáneas por tienda para evitar bloqueos
        limite_concurrencia = 5 
        semaforo = asyncio.Semaphore(limite_concurrencia)
        
        # Generar todas las tareas de golpe
        tareas = [
            self._fetch_single_card_with_semaphore(
                semaforo, client, tienda, carta, i, total_cartas, tienda_nombre
            )
            for i, carta in enumerate(cartas, 1)
        ]
        
        # Ejecutarlas concurrentemente respetando el semáforo
        resultados_brutos = await asyncio.gather(*tareas)
        
        # Aplanar lista de listas
        return [item for sublist in resultados_brutos for item in sublist]

    async def extraer_precios_batch(self, tiendas: List[str], cartas: List[str]) -> List[Dict]:
        logger.info(f"Iniciando extracción asíncrona CONCURRENTE TOTAL: {len(cartas)} cartas en {len(tiendas)} tiendas Shopify.")
        
        async with httpx.AsyncClient(headers=self.headers, timeout=30.0, follow_redirects=True) as client:
            tareas = [self._procesar_tienda(client, tienda, cartas) for tienda in tiendas]
            resultados_brutos = await asyncio.gather(*tareas)
            
            datos_consolidados = [item for sublist in resultados_brutos for item in sublist]
            logger.info(f"Extracción Shopify finalizada. {len(datos_consolidados)} variantes EN STOCK obtenidas.")
            return datos_consolidados