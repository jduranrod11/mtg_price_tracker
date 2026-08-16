import asyncio
import httpx
import json

async def investigar_reino_eldrazi():
    # Endpoint predictivo estándar de Shopify
    url_shopify = "https://reino-eldrazi.cl/search/suggest.json?q=akroma&resources[type]=product"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    }
    
    print(f"🔍 Lanzando sonda a la API nativa de Shopify en Reino Eldrazi...")
    print(f"URL: {url_shopify}\n")
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        try:
            response = await client.get(url_shopify)
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                datos = response.json()
                print("✅ ¡Bingo! La API nativa de Shopify está abierta. Aquí está la estructura:\n")
                # Imprimimos un extracto para analizar las llaves
                print(json.dumps(datos, indent=2)[:1500])
            else:
                print("❌ La API nativa está cerrada o modificada.")
                print("   Siguiente paso: Usar F12 en el navegador para cazar la API de su buscador.")
                
        except Exception as e:
            print(f"❌ Error de conexión: {e}")

if __name__ == "__main__":
    asyncio.run(investigar_reino_eldrazi())