"""
Lógica de negocio de "Dólar Efectivo".

Compara el precio local (CLP) de cada carta contra el benchmark internacional
de Card Kingdom (USD) para determinar el tipo de cambio implícito que se está
pagando en cada tienda local. Es la fuente única de esta lógica: tanto
`dashboard.py` como `reporte_oportunidades.py` la reutilizan para no divergir
en los umbrales/tasa de cambio (CLAUDE.md, Reglas de Negocio Críticas #3).
"""
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

from src.config import TASA_USD_CLP_REFERENCIA

# Umbrales de evaluación del Dólar Efectivo. La tasa de referencia CLP/USD
# vive en `src.config` (único lugar donde se parametriza, CLAUDE.md #3) y
# la reexportamos aquí para no romper a quien ya la importaba desde este
# módulo.
UMBRAL_CONVENIENTE = 800
UMBRAL_MERCADO = 850

QUERY_PRECIOS_VIGENTES = """
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


def cargar_precios_vigentes(engine: Engine) -> pd.DataFrame:
    """Trae el último snapshot de precios de cada tienda (independiente entre sí,
    CLAUDE.md, Reglas de Negocio Críticas #2).

    `Fecha_Registro` sale siempre como UTC con zona explícita: SQLite guarda la
    marca sin zona y quien la consuma no tiene cómo saber que es UTC, que es
    justo lo que hacía que el dashboard le sumara horas de antigüedad falsa.
    """
    df = pd.read_sql_query(QUERY_PRECIOS_VIGENTES, engine)

    if 'Fecha_Registro' in df.columns:
        df['Fecha_Registro'] = pd.to_datetime(df['Fecha_Registro'], utc=True)

    return df


def a_hora_local(fechas: pd.Series) -> pd.Series:
    """Convierte marcas UTC a la zona horaria del equipo, solo para presentarlas."""
    zona_local = datetime.now().astimezone().tzinfo
    return fechas.dt.tz_convert(zona_local)


def _evaluar_oportunidad(row, umbral_conveniente: float, umbral_mercado: float) -> str:
    if pd.isna(row['CK_USD']) or row['CK_USD'] == 0:
        return "⚪ Sin Ref."
    if row['Dolar_Efectivo'] < umbral_conveniente:
        return "🟢 Conveniente"
    if row['Dolar_Efectivo'] <= umbral_mercado:
        return "🟡 Mercado"
    return "🔴 Sobreprecio"


def calcular_benchmark_dolar_efectivo(
    df: pd.DataFrame,
    tasa_ref: float = TASA_USD_CLP_REFERENCIA,
    umbral_conveniente: float = UMBRAL_CONVENIENTE,
    umbral_mercado: float = UMBRAL_MERCADO,
) -> pd.DataFrame:
    """Calcula el Dólar Efectivo por carta: el mejor precio local (CLP) dividido
    por el precio de Card Kingdom en USD (convertido con `tasa_ref`).

    Devuelve un DataFrame vacío si no hay precios locales con los que comparar.
    """
    is_ck = df['Tienda'].str.contains('cardkingdom', case=False)
    df_ck = df[is_ck].copy()
    df_local = df[~is_ck].copy()

    df_ck_min = (
        df_ck.loc[df_ck.groupby('Carta')['Precio_CLP'].idxmin()][['Carta', 'Precio_CLP']]
        .rename(columns={'Precio_CLP': 'Precio_CK_CLP'})
        if not df_ck.empty else pd.DataFrame(columns=['Carta', 'Precio_CK_CLP'])
    )
    df_local_min = (
        df_local.loc[df_local.groupby('Carta')['Precio_CLP'].idxmin()].copy()
        if not df_local.empty else pd.DataFrame()
    )

    if df_local_min.empty:
        return pd.DataFrame()

    df_benchmark = pd.merge(df_local_min, df_ck_min, on='Carta', how='left')
    df_benchmark['CK_USD'] = df_benchmark['Precio_CK_CLP'] / tasa_ref
    df_benchmark['Dolar_Efectivo'] = np.where(
        (df_benchmark['CK_USD'] > 0) & df_benchmark['CK_USD'].notna(),
        df_benchmark['Precio_CLP'] / df_benchmark['CK_USD'],
        np.nan
    )
    df_benchmark['Evaluación'] = df_benchmark.apply(
        _evaluar_oportunidad, axis=1, umbral_conveniente=umbral_conveniente, umbral_mercado=umbral_mercado
    )
    return df_benchmark


def top_oportunidades(df_benchmark: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Las N mejores oportunidades del día: menor Dólar Efectivo con referencia
    válida de Card Kingdom, de mejor a peor."""
    if df_benchmark.empty:
        return df_benchmark

    validas = df_benchmark[df_benchmark['CK_USD'].notna() & (df_benchmark['CK_USD'] > 0)]
    return validas.sort_values('Dolar_Efectivo', ascending=True).head(n)
