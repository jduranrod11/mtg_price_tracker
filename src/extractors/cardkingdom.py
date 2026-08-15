import asyncio
import httpx
from typing import List, Dict
from src.utils.logger import get_logger

logger = get_logger(__name__)

class CardKingdomExtractor:
    def __init__(self, delay_entre_peticiones: float = 0, tasa_usd_clp: int = 800):
        # Endpoint de la API pública v2 de Card Kingdom
        self.api_url = "https://api.cardkingdom.com/api/v2/pricelist"
        self.tasa_usd_clp = tasa_usd_clp
        self._catalogo_cache = None # Aquí guardaremos el JSON gigante

    async def _descargar_catalogo(self):
        """Descarga el JSON de Card Kingdom a la memoria RAM una sola vez."""
        if self._catalogo_cache is not None:
            return self._catalogo_cache
            
        logger.info("⏳ Descargando catálogo de la API de Card Kingdom (esto tomará unos segundos)...")
        
        # Aumentamos el timeout porque el JSON completo es pesado
        async with httpx.AsyncClient(http2=True, timeout=60.0) as client:
            try:
                response = await client.get(self.api_url)
                response.raise_for_status()
                datos = response.json()
                
                # La lista de cartas viene en el nodo 'data'
                self._catalogo_cache = datos.get('data', [])
                logger.info(f"✅ Catálogo CK en memoria: {len(self._catalogo_cache)} cartas disponibles.")
            except Exception as e:
                logger.error(f"❌ Error descargando la API de Card Kingdom: {e}")
                self._catalogo_cache = []
                
        return self._catalogo_cache

    async def extraer_precios_batch(self, tiendas: List[str], cartas: List[str]) -> List[Dict]:
        catalogo = await self._descargar_catalogo()
        resultados = []
        
        if not catalogo:
            return resultados

        # Normalizar a minúsculas para un match más rápido
        cartas_buscadas_lower = [c.lower() for c in cartas]
        
        # Como es nuestra tienda de referencia, la URL base es estándar
        tienda_url = tiendas[0].rstrip('/') if tiendas else "https://www.cardkingdom.com"
        
        logger.info(f"[{tienda_url.replace('https://www.', '')}] Buscando {len(cartas)} cartas en el catálogo interno...")

        # Escanear el catálogo en RAM
        for item in catalogo:
            nombre_ck = item.get('name', '')
            
            # Comprobar si el nombre de CK coincide con alguna de nuestras cartas objetivo
            match_idx = next((i for i, c in enumerate(cartas_buscadas_lower) if c in nombre_ck.lower()), None)
            
            if match_idx is not None:
                carta_objetivo = cartas[match_idx]
                edicion = item.get('edition', 'Unknown')
                
                # Determinar si es Foil
                es_foil = str(item.get('is_foil', 'false')).lower() == 'true'
                acabado = "Foil" if es_foil else "No Foil"

                # 1. Extraer precio Near Mint (NM)
                # Ojo: A veces usan 'sell_nm', a veces 'price_retail'
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