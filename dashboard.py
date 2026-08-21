import streamlit as st
import pandas as pd
import requests
import urllib.parse
from datetime import datetime
from pathlib import Path

from src.db import engine
from src.analytics import (
    TASA_USD_CLP_REFERENCIA,
    a_hora_local,
    cargar_precios_vigentes,
    calcular_benchmark_dolar_efectivo,
    top_oportunidades,
)
from reporte_oportunidades import generar_reporte
from src.utils.logger import get_logger

logger = get_logger(__name__)

APP_VERSION = "1.0.0"
UMBRAL_FRESCURA_HORAS = 48  # A partir de cuántas horas sin actualizar avisamos que una tienda quedó atrás

# 1. Configuración de la página
st.set_page_config(page_title="MTG Price Tracker", layout="wide", page_icon="🧙‍♂️")

@st.cache_data(ttl=60)
def load_data() -> pd.DataFrame:
    # Rescata la última ejecución INDEPENDIENTE de cada tienda (CLAUDE.md #2)
    try:
        return cargar_precios_vigentes(engine)
    except Exception as e:
        logger.error(f"Error cargando base de datos: {e}", exc_info=True)
        st.error(f"Error cargando base de datos: {e}")
        return pd.DataFrame()

df = load_data()

col_titulo, col_refrescar = st.columns([5, 1])
with col_titulo:
    st.title("🧙‍♂️ MTG Price Tracker - Mercado Secundario")
with col_refrescar:
    st.write("")
    st.button(
        "🔄 Refrescar datos",
        on_click=load_data.clear,
        use_container_width=True,
        help="Limpia el caché (60s) y vuelve a consultar la base de datos. Útil justo después de correr `uv run main.py`.",
    )

# --- SESIÓN HTTP REUTILIZABLE PARA SCRYFALL (evita reabrir conexión en cada carta) ---
_scryfall_session = requests.Session()

# --- FUNCIÓN PARA OBTENER IMÁGENES DE SCRYFALL ---
@st.cache_data(ttl=86400) # Cacheamos por 24 hrs para que la app vuele y no saturar Scryfall
def get_scryfall_image_url(carta_nombre: str, edicion: str = None) -> str:
    try:
        if edicion:
            # 1. Intentamos buscar la carta exacta por Nombre y Edición
            query = f'!"{carta_nombre}" set:"{edicion}"'
            url = f"https://api.scryfall.com/cards/search?q={urllib.parse.quote_plus(query)}"
            res = _scryfall_session.get(url, timeout=5)
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
    except Exception as e:
        # 3. Fallback de emergencia
        logger.warning(f"Fallo consultando imagen en Scryfall para '{carta_nombre}' [{edicion}]: {e}")
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

    # --- Frescura de los datos por tienda (CLAUDE.md #2: cada tienda corre independiente) ---
    # `Fecha_Registro` llega en UTC con zona explícita: la antigüedad se calcula
    # contra un "ahora" también en UTC y solo se convierte a local para mostrarla.
    ultima_actualizacion = df.groupby('Tienda')['Fecha_Registro'].max().reset_index()
    ultima_actualizacion['Horas desde la última extracción'] = (
        (pd.Timestamp.now(tz='UTC') - ultima_actualizacion['Fecha_Registro']).dt.total_seconds() / 3600
    )
    ultima_actualizacion['Fecha_Registro'] = a_hora_local(ultima_actualizacion['Fecha_Registro'])

    tiendas_desactualizadas = ultima_actualizacion[ultima_actualizacion['Horas desde la última extracción'] > UMBRAL_FRESCURA_HORAS]
    if not tiendas_desactualizadas.empty:
        lista_tiendas = ", ".join(tiendas_desactualizadas['Tienda'])
        st.warning(f"⚠️ Llevan más de {UMBRAL_FRESCURA_HORAS}h sin actualizarse: {lista_tiendas}")

    with st.expander("🕒 Última actualización por tienda"):
        st.dataframe(
            ultima_actualizacion.rename(columns={'Fecha_Registro': 'Última extracción'}),
            use_container_width=True, hide_index=True,
            column_config={
                "Horas desde la última extracción": st.column_config.NumberColumn(format="%.1f h"),
            },
        )

    st.divider()

    # --- TOP 5 OPORTUNIDADES DEL DÍA (global, no depende de los filtros laterales) ---
    col_titulo_top5, col_accion_top5 = st.columns([4, 1])
    with col_titulo_top5:
        st.subheader("🥇 Top 5 Oportunidades del Día (Dólar Efectivo)")
        st.caption("Ranking global de todo el catálogo rastreado hoy. No se ve afectado por los filtros laterales.")
    with col_accion_top5:
        if st.button("🔄 Generar reporte", use_container_width=True):
            with st.spinner("Generando reporte..."):
                ruta_reporte = generar_reporte(engine=engine)
            if ruta_reporte:
                st.success(f"Reporte guardado en `{ruta_reporte}`")
            else:
                st.warning("No hay datos suficientes todavía para generar el reporte.")

    df_benchmark_global = calcular_benchmark_dolar_efectivo(df, tasa_ref=TASA_USD_CLP_REFERENCIA)
    df_top5 = top_oportunidades(df_benchmark_global, n=5)

    if df_top5.empty:
        st.info("Todavía no hay suficientes precios locales y de Card Kingdom para calcular oportunidades.")
    else:
        cols_top5 = st.columns(len(df_top5))
        for rank, (col, (_, row)) in enumerate(zip(cols_top5, df_top5.iterrows()), start=1):
            with col:
                img_url = get_scryfall_image_url(row['Carta'], row['Edicion'])
                st.image(img_url, use_container_width=True)
                st.markdown(f"**#{rank} · {row['Carta']}**")
                st.caption(f"{row['Tienda']} — {row['Edicion'] or 'Edición no especificada'}")
                ahorro_pct = (TASA_USD_CLP_REFERENCIA - row['Dolar_Efectivo']) / TASA_USD_CLP_REFERENCIA * 100
                st.metric(
                    "Dólar Efectivo",
                    f"${row['Dolar_Efectivo']:,.0f}".replace(',', '.'),
                    delta=f"{ahorro_pct:+.1f}% vs. ${TASA_USD_CLP_REFERENCIA}",
                )
                st.caption(row['Evaluación'])

    reporte_hoy = Path("reportes") / f"oportunidades_{datetime.now().strftime('%Y-%m-%d')}.md"
    if reporte_hoy.exists():
        st.download_button(
            "📄 Descargar reporte Markdown de hoy",
            data=reporte_hoy.read_text(encoding='utf-8'),
            file_name=reporte_hoy.name,
            mime="text/markdown",
        )

    st.divider()

    st.subheader("🏆 Oportunidades de Compra vs. Mercado (Card Kingdom)")

    df_benchmark = calcular_benchmark_dolar_efectivo(df_filtrado, tasa_ref=TASA_USD_CLP_REFERENCIA)

    if not df_benchmark.empty:
        df_resumen = df_benchmark.groupby('Tienda')['Precio_CLP'].sum().reset_index()
        df_resumen.loc[len(df_resumen)] = ['TOTAL', df_resumen['Precio_CLP'].sum()]
        df_resumen.columns = ['Tienda / Resumen', 'Monto a Pagar']

        # --- MAQUETACIÓN INTERACTIVA ---
        col_img, col_data_resumen, col_data_detalle = st.columns([1, 1.2, 3])

        # 1. Reservamos el espacio visual para la imagen a la izquierda
        img_placeholder = col_img.empty()

        with col_data_resumen:
            st.markdown("**🛒 Carrito Optimizado**")
            st.dataframe(
                df_resumen,
                use_container_width=True, hide_index=True,
                column_config={
                    "Monto a Pagar": st.column_config.NumberColumn("Monto a Pagar", format="$%d CLP"),
                },
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

    col_titulo_catalogo, col_descarga_catalogo = st.columns([4, 1])
    with col_titulo_catalogo:
        st.subheader("📋 Catálogo Vigente Completo")
    df_display = df_filtrado.copy()
    df_display['Fecha_Registro'] = a_hora_local(df_display['Fecha_Registro']).dt.strftime('%Y-%m-%d %H:%M')
    with col_descarga_catalogo:
        st.write("")
        st.download_button(
            "⬇️ Descargar CSV",
            data=df_display.to_csv(index=False).encode('utf-8-sig'),
            file_name=f"catalogo_vigente_{datetime.now().strftime('%Y-%m-%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.dataframe(
        df_display,
        use_container_width=True, hide_index=True,
        column_config={
            "Precio_CLP": st.column_config.NumberColumn("Precio_CLP", format="$%d CLP"),
        },
    )

    st.divider()
    st.caption(
        f"MTG Price Tracker v{APP_VERSION} · Tasa de referencia CLP/USD: {TASA_USD_CLP_REFERENCIA} · "
        f"Datos vigentes al {a_hora_local(df['Fecha_Registro']).max().strftime('%Y-%m-%d %H:%M')} (hora local)"
    )
