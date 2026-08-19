import streamlit as st
import pandas as pd
import numpy as np
import urllib.parse
import requests
from sqlalchemy import create_engine

# 1. Configuración de la página
st.set_page_config(page_title="MTG Price Tracker", layout="wide", page_icon="🧙‍♂️")
st.title("🧙‍♂️ MTG Price Tracker - Mercado Secundario")

# 2. Conexión a la Base de Datos
engine = create_engine("sqlite:///mtg_tracker.db")

@st.cache_data(ttl=60)
def load_data():
    # Nueva consulta SQL: Rescata la última ejecución INDEPENDIENTE de cada tienda
    query = """
        WITH UltimaExtraccionPorTienda AS (
            SELECT tienda_id, MAX(ejecucion_id) as last_run 
            FROM fact_precios
            GROUP BY tienda_id
        ),
        PreciosVigentes AS (
            SELECT 
                c.nombre AS Carta,
                c.mazo AS Mazo,
                t.nombre AS Tienda,
                p.edicion AS Edicion,
                p.acabado AS Acabado,
                p.idioma AS Idioma,
                p.estado AS Estado,
                p.variantes AS Variantes,
                p.precio_clp,
                p.fecha_extraccion
            FROM fact_precios p
            JOIN dim_cartas c ON p.carta_id = c.id
            JOIN dim_tiendas t ON p.tienda_id = t.id
            JOIN UltimaExtraccionPorTienda ue 
                ON p.tienda_id = ue.tienda_id 
                AND p.ejecucion_id = ue.last_run
        )
        SELECT 
            Carta, Mazo, Tienda, Edicion, Acabado, Idioma, Estado, Variantes, 
            MIN(precio_clp) AS Precio_CLP, 
            MAX(fecha_extraccion) AS Fecha_Registro
        FROM PreciosVigentes
        GROUP BY 
            Carta, Mazo, Tienda, Edicion, Acabado, Idioma, Estado, Variantes
        ORDER BY 
            Carta ASC, Precio_CLP ASC
    """
    try:
        df = pd.read_sql_query(query, engine)
        return df
    except Exception as e:
        st.error(f"Error cargando base de datos: {e}")
        return pd.DataFrame()
    
df = load_data()

# --- FUNCIÓN PARA OBTENER IMÁGENES DE SCRYFALL ---
@st.cache_data(ttl=86400) # Cacheamos por 24 hrs para que la app vuele y no saturar Scryfall
def get_scryfall_image_url(carta_nombre: str, edicion: str = None) -> str:
    try:
        if edicion:
            # 1. Intentamos buscar la carta exacta por Nombre y Edición
            query = f'!"{carta_nombre}" set:"{edicion}"'
            url = f"https://api.scryfall.com/cards/search?q={urllib.parse.quote_plus(query)}"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data.get('data'):
                    card_data = data['data'][0] # Tomamos el primer match
                    if 'image_uris' in card_data:
                        return card_data['image_uris'].get('normal')
                    elif 'card_faces' in card_data: # Soporte para cartas de doble cara
                        return card_data['card_faces'][0]['image_uris'].get('normal')

        # 2. Fallback: Si no hay edición, o la API no encontró el match exacto de la edición,
        # pedimos la imagen por defecto usando el endpoint rápido 'named'
        safe_name = urllib.parse.quote_plus(carta_nombre)
        return f"https://api.scryfall.com/cards/named?exact={safe_name}&format=image&version=normal"
    except Exception:
        # 3. Fallback de emergencia
        safe_name = urllib.parse.quote_plus(carta_nombre)
        return f"https://api.scryfall.com/cards/named?exact={safe_name}&format=image&version=normal"

# 3. Interfaz Visual
if df.empty:
    st.warning("La base de datos está vacía o no existe. Ejecuta el pipeline (`uv run main.py`) primero.")
else:
    # --- Filtros Laterales ---
    st.sidebar.header("Filtros de Búsqueda")

    mazos_disponibles = sorted(df['Mazo'].dropna().unique())
    mazos_seleccionados = st.sidebar.multiselect("Filtrar por Mazo", options=mazos_disponibles)

    cartas_seleccionadas = st.sidebar.multiselect("Filtrar por Carta", options=sorted(df['Carta'].unique()))
    tiendas_seleccionadas = st.sidebar.multiselect("Filtrar por Tienda", options=sorted(df['Tienda'].unique()))
    
    # Aplicar filtros secuencialmente
    df_filtrado = df.copy()
    if mazos_seleccionados:
        df_filtrado = df_filtrado[df_filtrado['Mazo'].isin(mazos_seleccionados)]
    if cartas_seleccionadas:
        df_filtrado = df_filtrado[df_filtrado['Carta'].isin(cartas_seleccionadas)]
    if tiendas_seleccionadas:
        df_filtrado = df_filtrado[df_filtrado['Tienda'].isin(tiendas_seleccionadas)]

    # --- Métricas Generales ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Cartas Buscadas", df_filtrado['Carta'].nunique())
    col2.metric("Tiendas Extraídas", df_filtrado['Tienda'].nunique())
    col3.metric("Ofertas Activas (Último Stock)", len(df_filtrado))
    
    st.divider()

    st.subheader("🏆 Oportunidades de Compra vs. Mercado (Card Kingdom)")
    
    # Cálculos de Benchmark (Sin cambios)
    is_ck = df_filtrado['Tienda'].str.contains('cardkingdom', case=False)
    df_ck = df_filtrado[is_ck].copy()
    df_local = df_filtrado[~is_ck].copy()
    
    df_ck_min = df_ck.loc[df_ck.groupby('Carta')['Precio_CLP'].idxmin()][['Carta', 'Precio_CLP']].rename(columns={'Precio_CLP': 'Precio_CK_CLP'}) if not df_ck.empty else pd.DataFrame(columns=['Carta', 'Precio_CK_CLP'])
    df_local_min = df_local.loc[df_local.groupby('Carta')['Precio_CLP'].idxmin()].copy() if not df_local.empty else pd.DataFrame()

    if not df_local_min.empty:
        df_benchmark = pd.merge(df_local_min, df_ck_min, on='Carta', how='left')
        tasa_ref = 800
        df_benchmark['CK_USD'] = df_benchmark['Precio_CK_CLP'] / tasa_ref
        df_benchmark['Dolar_Efectivo'] = np.where(
            (df_benchmark['CK_USD'] > 0) & df_benchmark['CK_USD'].notna(),
            df_benchmark['Precio_CLP'] / df_benchmark['CK_USD'],
            np.nan
        )
        
        def evaluar_oportunidad(row):
            if pd.isna(row['CK_USD']) or row['CK_USD'] == 0: return "⚪ Sin Ref."
            if row['Dolar_Efectivo'] < 800: return "🟢 Conveniente"
            if row['Dolar_Efectivo'] <= 850: return "🟡 Mercado"
            return "🔴 Sobreprecio"
            
        df_benchmark['Evaluación'] = df_benchmark.apply(evaluar_oportunidad, axis=1)
        
        df_resumen = df_local_min.groupby('Tienda')['Precio_CLP'].sum().reset_index()
        df_resumen.loc[len(df_resumen)] = ['TOTAL', df_resumen['Precio_CLP'].sum()]
        df_resumen.columns = ['Tienda / Resumen', 'Monto a Pagar']

        # --- MAQUETACIÓN INTERACTIVA ---
        col_img, col_data_resumen, col_data_detalle = st.columns([1, 1.2, 3])
        
        # 1. Reservamos el espacio visual para la imagen a la izquierda
        img_placeholder = col_img.empty()
            
        with col_data_resumen:
            st.markdown("**🛒 Carrito Optimizado**")
            st.dataframe(
                df_resumen.style.format({'Monto a Pagar': lambda x: f"${int(x):,} CLP".replace(',', '.')}), 
                use_container_width=True, hide_index=True
            )
            
        with col_data_detalle:
            st.markdown("**📊 Haz clic en una fila para ver la carta**")
            columnas_mostrar = ['Carta', 'Tienda', 'Edicion', 'Estado', 'Precio_CLP', 'CK_USD', 'Dolar_Efectivo', 'Evaluación']
            
            # Usamos st.column_config para formatear el dataframe en vez de .style
            # ya que es el método oficial recomendado para tablas interactivas
            config_columnas = {
                "Precio_CLP": st.column_config.NumberColumn("Precio_CLP", format="$%d CLP"),
                "CK_USD": st.column_config.NumberColumn("CK_USD", format="$%.2f"),
                "Dolar_Efectivo": st.column_config.NumberColumn("Dolar_Efectivo", format="$%d CLP"),
            }
            
            # 2. Dibujamos la tabla con on_select="rerun"
            event = st.dataframe(
                df_benchmark[columnas_mostrar], 
                use_container_width=True, 
                hide_index=True,
                on_select="rerun",           # <-- Activa la interactividad
                selection_mode="single-row", # <-- Solo permite seleccionar una carta a la vez
                column_config=config_columnas
            )
            
        # 3. Lógica para determinar qué carta inyectar en el espacio reservado
        if event.selection.rows:
            # Si hay un clic activo, tomamos el índice de la fila seleccionada
            fila_idx = event.selection.rows[0]
            carta_actual = df_benchmark.iloc[fila_idx]['Carta']
            edicion_actual = df_benchmark.iloc[fila_idx]['Edicion']
        else:
            # Si no hay clic, mostramos la primera carta de la tabla por defecto
            carta_actual = df_benchmark.iloc[0]['Carta']
            edicion_actual = df_benchmark.iloc[0]['Edicion']

        # 4. Inyectamos la imagen correspondiente en el contenedor izquierdo
        img_url = get_scryfall_image_url(carta_actual, edicion_actual)
        img_placeholder.image(img_url, use_container_width=True)

    st.divider()

    st.subheader("📋 Catálogo Vigente Completo")
    df_display = df_filtrado.copy()
    df_display['Fecha_Registro'] = pd.to_datetime(df_display['Fecha_Registro']).dt.strftime('%Y-%m-%d %H:%M')
    
    st.dataframe(
        df_display.style.format({'Precio_CLP': lambda x: f"${int(x):,} CLP".replace(',', '.')}), 
        use_container_width=True, hide_index=True
    )