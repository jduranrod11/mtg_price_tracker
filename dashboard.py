import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine

# 1. Configuración de la página
st.set_page_config(page_title="MTG Price Tracker", layout="wide", page_icon="🧙‍♂️")
st.title("🧙‍♂️ MTG Price Tracker - Mercado Secundario")

# 2. Conexión a la Base de Datos
engine = create_engine("sqlite:///mtg_tracker.db")

@st.cache_data(ttl=60)
def load_data():
    query = """
        WITH UltimaExtraccion AS (
            SELECT datetime(MAX(fecha_extraccion), '-5 minutes') as limite_inferior 
            FROM fact_precios
        ),
        UltimosPrecios AS (
            SELECT 
                c.nombre AS Carta,
                c.mazo AS Mazo,
                t.nombre AS Tienda,
                p.edicion AS Edicion,
                p.acabado AS Acabado,
                p.idioma AS Idioma,
                p.estado AS Estado,
                p.variantes AS Variantes,
                p.precio_clp AS Precio_CLP,
                p.fecha_extraccion AS Fecha_Registro,
                ROW_NUMBER() OVER (
                    PARTITION BY p.carta_id, p.tienda_id, p.edicion, p.acabado, p.idioma, p.estado, p.variantes 
                    ORDER BY p.fecha_extraccion DESC
                ) as rn
            FROM fact_precios p
            JOIN dim_cartas c ON p.carta_id = c.id
            JOIN dim_tiendas t ON p.tienda_id = t.id
        )
        SELECT 
            Carta, Mazo, Tienda, Edicion, Acabado, Idioma, Estado, Variantes, Precio_CLP, Fecha_Registro
        FROM UltimosPrecios
        CROSS JOIN UltimaExtraccion ue
        WHERE rn = 1 AND Fecha_Registro >= ue.limite_inferior
        ORDER BY Carta ASC, Precio_CLP ASC
    """
    try:
        df = pd.read_sql_query(query, engine)
        return df
    except Exception:
        return pd.DataFrame()

df = load_data()

# 3. Interfaz Visual
if df.empty:
    st.warning("La base de datos está vacía o no existe. Ejecuta el pipeline (`uv run main.py`) primero.")
else:
    # --- Métricas Generales ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Cartas Buscadas", df['Carta'].nunique())
    col2.metric("Tiendas Extraídas", df['Tienda'].nunique())
    col3.metric("Ofertas Activas (Último Stock)", len(df))
    
    st.divider()

    # --- Filtros Laterales ---
    st.sidebar.header("Filtros de Búsqueda")

    # Filtro por Mazo
    # Usamos dropna() por si hay cartas que aún no tienen un mazo asignado
    mazos_disponibles = sorted(df['Mazo'].dropna().unique())
    mazos_seleccionados = st.sidebar.multiselect("Filtrar por Mazo", options=mazos_disponibles)

    cartas_seleccionadas = st.sidebar.multiselect("Filtrar por Carta", options=sorted(df['Carta'].unique()))
    tiendas_seleccionadas = st.sidebar.multiselect("Filtrar por Tienda", options=sorted(df['Tienda'].unique()))
    
    df_filtrado = df.copy()
    if mazos_seleccionados:
        df_filtrado = df_filtrado[df_filtrado['Mazo'].isin(mazos_seleccionados)]

    if cartas_seleccionadas:
        df_filtrado = df_filtrado[df_filtrado['Carta'].isin(cartas_seleccionadas)]

    if tiendas_seleccionadas:
        df_filtrado = df_filtrado[df_filtrado['Tienda'].isin(tiendas_seleccionadas)]

    # --- Vista de Mejores Precios y Benchmark ---
    st.subheader("🏆 Oportunidades de Compra vs. Mercado (Card Kingdom)")
    
    # 1. Separar Card Kingdom (Benchmark) del mercado local (Chile)
    is_ck = df_filtrado['Tienda'].str.contains('cardkingdom', case=False)
    df_ck = df_filtrado[is_ck].copy()
    df_local = df_filtrado[~is_ck].copy()
    
    # 2. Obtener el precio mínimo de referencia (Card Kingdom) por carta
    if not df_ck.empty:
        idx_ck_min = df_ck.groupby('Carta')['Precio_CLP'].idxmin()
        df_ck_min = df_ck.loc[idx_ck_min][['Carta', 'Precio_CLP']].rename(columns={'Precio_CLP': 'Precio_CK_CLP'})
    else:
        df_ck_min = pd.DataFrame(columns=['Carta', 'Precio_CK_CLP'])

    # 3. Obtener el precio mínimo del mercado Local
    if not df_local.empty:
        idx_local_min = df_local.groupby('Carta')['Precio_CLP'].idxmin()
        df_local_min = df_local.loc[idx_local_min].copy()
    else:
        df_local_min = pd.DataFrame()

    # 4. Cruzar datos para el Benchmark Financiero
    if not df_local_min.empty:
        df_benchmark = pd.merge(df_local_min, df_ck_min, on='Carta', how='left')
        
        # Cálculos Financieros (Tasa Referencia = 800)
        tasa_ref = 800
        df_benchmark['CK_USD'] = df_benchmark['Precio_CK_CLP'] / tasa_ref
        
        # Evitar división por cero si CK_USD es 0 o nulo
        df_benchmark['Dolar_Efectivo'] = np.where(
            (df_benchmark['CK_USD'] > 0) & df_benchmark['CK_USD'].notna(),
            df_benchmark['Precio_CLP'] / df_benchmark['CK_USD'],
            np.nan
        )
        
        # Clasificador visual
        def evaluar_oportunidad(row):
            if pd.isna(row['CK_USD']) or row['CK_USD'] == 0:
                return "⚪ Sin Ref."
            if row['Dolar_Efectivo'] < 800:
                return "🟢 Conveniente"
            if row['Dolar_Efectivo'] <= 850:
                return "🟡 Mercado"
            return "🔴 Sobreprecio"
            
        df_benchmark['Evaluación'] = df_benchmark.apply(evaluar_oportunidad, axis=1)
        
        # Generar Carrito Resumen (Excluyendo Card Kingdom)
        df_resumen = df_local_min.groupby('Tienda')['Precio_CLP'].sum().reset_index()
        total_gasto = df_resumen['Precio_CLP'].sum()
        df_resumen.loc[len(df_resumen)] = ['TOTAL', total_gasto]
        df_resumen.columns = ['Tienda / Resumen', 'Monto a Pagar']

        # Renderizar Columnas
        col_resumen, col_detalle = st.columns([1.2, 3.5])
        
        with col_resumen:
            st.markdown("**🛒 Carrito Optimizado (Chile)**")
            st.dataframe(
                df_resumen.style.format({
                    'Monto a Pagar': lambda x: f"${int(x):,} CLP".replace(',', '.')
                }), 
                use_container_width=True, hide_index=True
            )
            
        with col_detalle:
            st.markdown("**📊 Análisis de Dólar Efectivo por Carta**")
            
            # Ordenamos y preparamos las columnas financieras
            columnas_mostrar = ['Carta', 'Mazo', 'Tienda', 'Estado', 'Precio_CLP', 'CK_USD', 'Dolar_Efectivo', 'Evaluación']
            
            st.dataframe(
                df_benchmark[columnas_mostrar].style.format({
                    'Precio_CLP': lambda x: f"${int(x):,} CLP".replace(',', '.'),
                    'CK_USD': lambda x: f"${x:,.2f}" if pd.notna(x) else "-",
                    'Dolar_Efectivo': lambda x: f"${int(x)} CLP" if pd.notna(x) else "-"
                }), 
                use_container_width=True, hide_index=True
            )

    st.divider()

    # --- Vista Detallada ---
    st.subheader("📋 Catálogo Vigente Completo")
    df_display = df_filtrado.copy()
    
    # Limpiar formato de fecha para la tabla
    df_display['Fecha_Registro'] = pd.to_datetime(df_display['Fecha_Registro']).dt.strftime('%Y-%m-%d %H:%M')
    
    # Formateo visual numérico para correcto ordenamiento
    st.dataframe(
        df_display.style.format({
            'Precio_CLP': lambda x: f"${int(x):,} CLP".replace(',', '.')
        }), 
        use_container_width=True, hide_index=True
    )