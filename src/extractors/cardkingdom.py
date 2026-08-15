import asyncio
import json
from typing import List, Dict
from playwright.async_api import async_playwright
from src.utils.logger import get_logger

logger = get_logger(__name__)

class CardKingdomExtractor:
    def __init__(self, delay_entre_peticiones: float = 0, tasa_usd_clp: int = 800):
        self.api_url = "https://api.cardkingdom.com/api/v2/pricelist"
        self.tasa_usd_clp = tasa_usd_clp
        self._catalogo_cache = None

    async def _descargar_catalogo(self):
        """Descarga el JSON usando un navegador VISIBLE para resolver desafíos de Cloudflare."""
        if self._catalogo_cache is not None:
            return self._catalogo_cache
            
        logger.info("⏳ Iniciando motor Playwright en modo VISIBLE para resolver Cloudflare...")
        
        try:
            async with async_playwright() as p:
                # Lanzamos Chromium de forma visible (headless=False)
                browser = await p.chromium.launch(headless=False)
                
                # Contexto con User-Agent de navegador estándar
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    viewport={'width': 1280, 'height': 720}
                )
                
                page = await context.new_page()
                
                logger.info("1. Entrando a la API de Card Kingdom. Si ves una casilla de verificación, ¡haz clic en ella!")
                await page.goto(self.api_url, wait_until="domcontentloaded")
                
                # Bucle de espera: Revisa cada segundo si ya tenemos el JSON en pantalla
                # Ampliamos a 30 segundos para darte tiempo de hacer clic si es necesario
                for intento in range(30):
                    try:
                        # Extraemos el texto visible de la pestaña actual
                        content = await page.evaluate("document.body.innerText")
                        datos = json.loads(content) # Intentamos parsearlo a Diccionario
                        
                        if 'data' in datos:
                            self._catalogo_cache = datos['data']
                            logger.info(f"✅ ¡Desafío JS Superado! Catálogo CK en memoria: {len(self._catalogo_cache)} cartas.")
                            break
                    except (json.JSONDecodeError, TypeError):
                        # Si no es JSON, seguimos en el desafío de Cloudflare. Esperamos y reintentamos.
                        if intento % 5 == 0 and intento > 0:
                            logger.info(f"   ... Aún resolviendo Cloudflare (Intento {intento}/30)")
                        await asyncio.sleep(1)
                        
                if not self._catalogo_cache:
                    logger.error("❌ El navegador no pudo pasar la verificación de Cloudflare a tiempo.")
                    self._catalogo_cache = []
                    
                await browser.close()
                
        except Exception as e:
            logger.error(f"❌ Error crítico ejecutando Playwright: {e}")
            self._catalogo_cache = []
                
        return self._catalogo_cache

    async def extraer_precios_batch(self, tiendas: List[str], cartas: List[str]) -> List[Dict]:
        catalogo = await self._descargar_catalogo()
        resultados = []
        
        if not catalogo:
            return resultados

        # Normalizar a minúsculas para un match más rápido
        cartas_buscadas_lower = [c.lower() for c in cartas]
        
        # URL base estándar
        tienda_url = tiendas[0].rstrip('/') if tiendas else "https://www.cardkingdom.com"
        
        logger.info(f"[{tienda_url.replace('https://www.', '')}] Buscando {len(cartas)} cartas en el catálogo interno...")

        # Escanear el catálogo en RAM a velocidad CPU
        for item in catalogo:
            nombre_ck = item.get('name', '')
            
            # Comprobar si el nombre de CK coincide con alguna de nuestras cartas
            match_idx = next((i for i, c in enumerate(cartas_buscadas_lower) if c in nombre_ck.lower()), None)
            
            if match_idx is not None:
                carta_objetivo = cartas[match_idx]
                edicion = item.get('edition', 'Unknown')
                es_foil = str(item.get('is_foil', 'false')).lower() == 'true'
                acabado = "Foil" if es_foil else "No Foil"

                # 1. Extraer precio Near Mint (NM)
                precio_nm_usd = float(item.get('sell_nm', 0.0) or item.get('price_retail', 0.0) or 0.0)
                if precio_nm_usd > 0:
                    resultados.append({
                        'tienda_url': tienda_url,
                        'carta_nombre': carta_objetivo,
                        'titulo_tienda': f"{nombre_ck} [{edicion}] EN NM {acabado}",
                        'precio_clp': precio_nm_usd * self.tasa_usd_clp
                    })
                    
                # 2. Extraer precio Excellent (Equivalente a nuestro Lightly Played / LP)
                precio_ex_usd = float(item.get('sell_ex', 0.0) or 0.0)
                if precio_ex_usd > 0:
                    resultados.append({
                        'tienda_url': tienda_url,
                        'carta_nombre': carta_objetivo,
                        'titulo_tienda': f"{nombre_ck} [{edicion}] EN LP {acabado}",
                        'precio_clp': precio_ex_usd * self.tasa_usd_clp
                    })

        return resultados