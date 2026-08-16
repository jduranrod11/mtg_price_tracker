from src.extractors.shopify import ShopifyExtractor
from src.extractors.woocommerce import WooCommerceExtractor
from src.extractors.cardkingdom import CardKingdomExtractor
from src.extractors.catlotus import CatLotusExtractor

class ExtractorFactory:
    @staticmethod
    def obtener_extractor(url_tienda: str):
        url = url_tienda.lower()
        
        # Clasificación manual basada en la auditoría
        tiendas_shopify = ["oasisgames.cl", "paytowin.cl", "reino-eldrazi.cl"]
        tiendas_woocommerce = ["huntercardtcg.com", "rhysticbazaar.cl", "lacripta.cl", "cardnexus.cl"]

        if "cardkingdom.com" in url:
            return CardKingdomExtractor(delay_entre_peticiones=0, tasa_usd_clp=800)

        elif "catlotus.cl" in url: # <--- Regla dedicada para Cat Lotus
            return CatLotusExtractor(delay_entre_peticiones=2.0)
        
        elif any(dominio in url for dominio in tiendas_shopify):
            return ShopifyExtractor(delay_entre_peticiones=1.5)
            
        elif any(dominio in url for dominio in tiendas_woocommerce):
            # ¡Ahora sí devolvemos el extractor instanciado!
            return WooCommerceExtractor(delay_entre_peticiones=2.0)
            
        else:
            return None