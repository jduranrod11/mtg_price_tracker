"""
Reporte Diario de Oportunidades - Dólar Efectivo.

Script independiente que se ejecuta al final del pipeline (`main.py`) para
destacar el Top N de mejores oportunidades de compra del día: cartas cuyo
precio local (CLP) implica el tipo de cambio más conveniente frente al
benchmark de Card Kingdom (USD).

También puede ejecutarse de forma manual en cualquier momento:
    uv run reporte_oportunidades.py
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy.engine import Engine

from src.db import engine as engine_default
from src.analytics import (
    TASA_USD_CLP_REFERENCIA,
    cargar_precios_vigentes,
    calcular_benchmark_dolar_efectivo,
    top_oportunidades,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _formatear_clp(valor: float) -> str:
    return f"${int(round(valor)):,}".replace(',', '.')


def _generar_markdown(df_top: pd.DataFrame, generado_en: datetime, tasa_ref: float) -> str:
    lineas = [
        "# 🏆 Reporte de Oportunidades del Día — Dólar Efectivo",
        "",
        f"Generado: {generado_en.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Tasa de referencia CLP/USD utilizada: {tasa_ref}",
        "",
        "Ranking de las mejores oportunidades de compra: menor **Dólar Efectivo** "
        "implica que la carta se está pagando, en pesos, a un tipo de cambio más "
        "barato que el de referencia frente al benchmark de Card Kingdom.",
        "",
        "| # | Carta | Mazo | Tienda | Edición | Precio Local | CK (USD) | Dólar Efectivo | Ahorro vs. Ref. | Evaluación |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for rank, (_, row) in enumerate(df_top.iterrows(), start=1):
        ahorro_pct = (tasa_ref - row['Dolar_Efectivo']) / tasa_ref * 100
        lineas.append(
            f"| {rank} | {row['Carta']} | {row.get('Mazo') or '-'} | {row['Tienda']} | "
            f"{row.get('Edicion') or '-'} | {_formatear_clp(row['Precio_CLP'])} | "
            f"${row['CK_USD']:.2f} | {_formatear_clp(row['Dolar_Efectivo'])} | "
            f"{ahorro_pct:+.1f}% | {row['Evaluación']} |"
        )

    lineas.append("")
    return "\n".join(lineas)


def generar_reporte(
    engine: Engine = engine_default,
    top_n: int = 5,
    output_dir: str = "reportes",
) -> Optional[Path]:
    """Calcula el Top N de oportunidades del día y lo guarda como Markdown.

    Devuelve el path del reporte generado, o None si no había datos suficientes
    (ej. base de datos vacía o sin benchmark de Card Kingdom todavía).
    """
    logger.info(f"Generando reporte de oportunidades (Top {top_n})...")

    df = cargar_precios_vigentes(engine)
    if df.empty:
        logger.warning("No hay precios vigentes en la base de datos. Se omite el reporte.")
        return None

    df_benchmark = calcular_benchmark_dolar_efectivo(df, tasa_ref=TASA_USD_CLP_REFERENCIA)
    if df_benchmark.empty:
        logger.warning("No hay precios locales para comparar contra el benchmark. Se omite el reporte.")
        return None

    df_top = top_oportunidades(df_benchmark, n=top_n)
    if df_top.empty:
        logger.warning("Ninguna carta tiene referencia de Card Kingdom válida hoy. Se omite el reporte.")
        return None

    generado_en = datetime.now()
    contenido = _generar_markdown(df_top, generado_en, TASA_USD_CLP_REFERENCIA)

    destino = Path(output_dir)
    destino.mkdir(parents=True, exist_ok=True)
    archivo_reporte = destino / f"oportunidades_{generado_en.strftime('%Y-%m-%d')}.md"
    archivo_reporte.write_text(contenido, encoding="utf-8")

    logger.info(f"Reporte generado: {archivo_reporte}")
    logger.info(f"--- TOP {len(df_top)} OPORTUNIDADES DEL DÍA ---")
    for rank, (_, row) in enumerate(df_top.iterrows(), start=1):
        logger.info(
            f"{rank}. {row['Carta']} [{row.get('Edicion') or '-'}] en {row['Tienda']}: "
            f"{_formatear_clp(row['Precio_CLP'])} (Dólar Efectivo: {_formatear_clp(row['Dolar_Efectivo'])} - {row['Evaluación']})"
        )

    return archivo_reporte


if __name__ == "__main__":
    generar_reporte()
