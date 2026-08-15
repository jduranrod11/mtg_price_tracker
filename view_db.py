import pandas as pd
from src.db.session import engine

def visualizar_base_datos():
    """
    Ejecuta un JOIN entre la tabla de hechos y las dimensiones 
    para mostrar un reporte legible en consola.
    """
    query = """
        SELECT 
            c.nombre AS Carta,
            t.nombre AS Tienda,
            p.edicion AS Edicion,
            p.acabado AS Acabado,
            p.idioma AS Idioma,
            p.variantes AS Variantes,
            p.precio_clp AS Precio_CLP,
            p.fecha_extraccion AS Fecha_Registro
        FROM fact_precios p
        JOIN dim_cartas c ON p.carta_id = c.id
        JOIN dim_tiendas t ON p.tienda_id = t.id
        ORDER BY c.nombre ASC, p.precio_clp ASC
    """
    
    # Pandas lee directamente desde el engine de SQLAlchemy
    df = pd.read_sql_query(query, engine)
    
    if df.empty:
        print("La base de datos está vacía.")
        return

    # Formateo visual del precio a pesos chilenos
    df['Precio_CLP'] = df['Precio_CLP'].apply(lambda x: f"${int(x):,}".replace(',', '.'))
    # Acortar la fecha para que no ocupe tanto espacio
    df['Fecha_Registro'] = pd.to_datetime(df['Fecha_Registro']).dt.strftime('%Y-%m-%d %H:%M')
    
    print("\n" + "="*80)
    print(" 📊 VISOR DE BASE DE DATOS: HISTORIAL DE PRECIOS MTG")
    print("="*80)
    print(df.to_string(index=False))

if __name__ == "__main__":
    visualizar_base_datos()