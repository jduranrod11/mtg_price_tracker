import asyncio
import httpx
import json

async def test_woocommerce_api():
    # Endpoint nativo de WooCommerce Store API
    url = "https://cardnexus.cl/wp-json/wc/store/products?search=akromas+memorial"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'es-CL,es;q=0.9,en;q=0.8'
    }
    
    print(f"🌐 Consultando API nativa de WooCommerce: {url}\n")
    
    async with httpx.AsyncClient(headers=headers, http2=True, follow_redirects=True) as client:
        response = await client.get(url)
        
        if response.status_code == 200:
            productos = response.json()
            print(f"✅ ¡API Abierta! Se encontraron {len(productos)} productos.")
            
            for prod in productos:
                print(f"\n--- {prod.get('name')} ---")
                print(f"Tipo: {prod.get('type')} | SKU: {prod.get('sku')}")
                
                # Precios base
                precios = prod.get('prices', {})
                print(f"Precio Base: {precios.get('price')} {precios.get('currency_code')}")
                
                # Revisar si tiene variantes (como Estado o Idioma)
                if prod.get('has_options'):
                    print("Atributos disponibles:")
                    print(json.dumps(prod.get('attributes', []), indent=2))
        else:
            print(f"❌ La API Store está cerrada o bloqueada. Código HTTP: {response.status_code}")
            print(response.text[:200])

if __name__ == "__main__":
    asyncio.run(test_woocommerce_api())