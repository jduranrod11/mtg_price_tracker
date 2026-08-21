"""Normalización de precios a CLP reales.

La escala la declara cada API, nunca se infiere del valor: la heurística anterior
("divide por 100 si es >1.000 y múltiplo de 100") convertía un precio real de
$25.000 en $250 apenas una tienda cotizara en cifras redondas.
"""
import pytest
from src.extractors.base import BaseExtractor


@pytest.mark.parametrize("precio_api, unidad_menor, esperado", [
    # Shopify `.js`: siempre centésimas
    (2499000, 2, 24990.0),
    (3950000, 2, 39500.0),
    (898600, 2, 8986.0),
    (2500000, 2, 25000.0),
    # WooCommerce en CLP: currency_minor_unit = 0
    ("2690", 0, 2690.0),
    ("24990", 0, 24990.0),
    ("25000", 0, 25000.0),   # Antes se guardaba como $250
    ("1500", 0, 1500.0),     # Antes se guardaba como $15
])
def test_la_escala_viene_de_la_api_no_del_valor(precio_api, unidad_menor, esperado):
    assert BaseExtractor._normalizar_precio_clp(precio_api, unidad_menor) == esperado


def test_shopify_es_el_caso_por_defecto():
    assert BaseExtractor._normalizar_precio_clp(2499000) == 24990.0
