"""
Tests de la lógica de negocio "Dólar Efectivo" (src/analytics/dolar_efectivo.py).

Es el cálculo más crítico del proyecto -- decide qué cartas se consideran
buenas oportunidades de compra -- y hasta ahora no tenía cobertura.
"""
import pandas as pd
import pytest

from src.analytics.dolar_efectivo import calcular_benchmark_dolar_efectivo, top_oportunidades


def _fila(carta, tienda, precio_clp, edicion="Edicion X", mazo="Mazo Test"):
    return {
        'Carta': carta,
        'Mazo': mazo,
        'Tienda': tienda,
        'Edicion': edicion,
        'Acabado': 'No Foil',
        'Idioma': 'EN',
        'Estado': 'NM',
        'Variantes': None,
        'Precio_CLP': precio_clp,
        'Fecha_Registro': '2026-08-18 12:00:00',
    }


def test_carta_conveniente_por_debajo_de_800():
    # CK vende a 10 USD (=8.000 CLP a tasa 800). Pagar 6.000 CLP local implica
    # un dólar efectivo de 600, por debajo del umbral de 800 -> Conveniente.
    df = pd.DataFrame([
        _fila('Lightning Bolt', 'cardkingdom.com', 8000),
        _fila('Lightning Bolt', 'tiendalocal.cl', 6000),
    ])
    resultado = calcular_benchmark_dolar_efectivo(df, tasa_ref=800)
    fila = resultado.iloc[0]
    assert fila['Dolar_Efectivo'] == pytest.approx(600.0)
    assert fila['Evaluación'] == "🟢 Conveniente"


def test_carta_en_rango_de_mercado():
    # Dólar efectivo de 820 cae dentro de [800, 850] -> Mercado.
    df = pd.DataFrame([
        _fila('Ugin, the Spirit Dragon', 'cardkingdom.com', 8000),
        _fila('Ugin, the Spirit Dragon', 'tiendalocal.cl', 8200),
    ])
    resultado = calcular_benchmark_dolar_efectivo(df, tasa_ref=800)
    assert resultado.iloc[0]['Evaluación'] == "🟡 Mercado"


def test_carta_con_sobreprecio():
    df = pd.DataFrame([
        _fila('Ulamog, the Infinite Gyre', 'cardkingdom.com', 8000),
        _fila('Ulamog, the Infinite Gyre', 'tiendalocal.cl', 9000),
    ])
    resultado = calcular_benchmark_dolar_efectivo(df, tasa_ref=800)
    assert resultado.iloc[0]['Evaluación'] == "🔴 Sobreprecio"


def test_carta_sin_referencia_de_card_kingdom():
    # Solo hay precio local, ninguna tienda 'cardkingdom' la vende.
    df = pd.DataFrame([_fila('Carta Exclusiva Local', 'tiendalocal.cl', 5000)])
    resultado = calcular_benchmark_dolar_efectivo(df, tasa_ref=800)
    fila = resultado.iloc[0]
    assert pd.isna(fila['Dolar_Efectivo'])
    assert fila['Evaluación'] == "⚪ Sin Ref."


def test_toma_el_precio_local_minimo_entre_varias_tiendas():
    df = pd.DataFrame([
        _fila('Skullclamp', 'cardkingdom.com', 8000),
        _fila('Skullclamp', 'tiendaA.cl', 7000),
        _fila('Skullclamp', 'tiendaB.cl', 5000),  # la más barata debe ganar
    ])
    resultado = calcular_benchmark_dolar_efectivo(df, tasa_ref=800)
    assert resultado.iloc[0]['Precio_CLP'] == 5000
    assert resultado.iloc[0]['Tienda'] == 'tiendaB.cl'


def test_sin_precios_locales_devuelve_dataframe_vacio():
    df = pd.DataFrame([_fila('Solo En Card Kingdom', 'cardkingdom.com', 8000)])
    resultado = calcular_benchmark_dolar_efectivo(df, tasa_ref=800)
    assert resultado.empty


def test_dataframe_vacio_no_revienta():
    columnas = ['Carta', 'Mazo', 'Tienda', 'Edicion', 'Acabado', 'Idioma', 'Estado', 'Variantes', 'Precio_CLP', 'Fecha_Registro']
    df = pd.DataFrame(columns=columnas)
    resultado = calcular_benchmark_dolar_efectivo(df, tasa_ref=800)
    assert resultado.empty


def test_top_oportunidades_ordena_de_mejor_a_peor():
    df = pd.DataFrame([
        _fila('Carta Cara', 'cardkingdom.com', 8000),
        _fila('Carta Cara', 'tiendalocal.cl', 9000),   # Dólar Efectivo alto (peor)
        _fila('Carta Barata', 'cardkingdom.com', 8000),
        _fila('Carta Barata', 'tiendalocal.cl', 4000),  # Dólar Efectivo bajo (mejor)
    ])
    benchmark = calcular_benchmark_dolar_efectivo(df, tasa_ref=800)
    top = top_oportunidades(benchmark, n=5)
    assert list(top['Carta']) == ['Carta Barata', 'Carta Cara']


def test_top_oportunidades_excluye_las_sin_referencia():
    df = pd.DataFrame([
        _fila('Con Referencia', 'cardkingdom.com', 8000),
        _fila('Con Referencia', 'tiendalocal.cl', 4000),
        _fila('Sin Referencia', 'tiendalocal.cl', 100),  # sin fila en cardkingdom.com
    ])
    benchmark = calcular_benchmark_dolar_efectivo(df, tasa_ref=800)
    top = top_oportunidades(benchmark, n=5)
    assert list(top['Carta']) == ['Con Referencia']


def test_top_oportunidades_respeta_el_limite_n():
    filas = []
    for i in range(10):
        filas.append(_fila(f'Carta {i}', 'cardkingdom.com', 8000))
        filas.append(_fila(f'Carta {i}', 'tiendalocal.cl', 1000 + i * 100))
    df = pd.DataFrame(filas)
    benchmark = calcular_benchmark_dolar_efectivo(df, tasa_ref=800)
    top = top_oportunidades(benchmark, n=3)
    assert len(top) == 3
