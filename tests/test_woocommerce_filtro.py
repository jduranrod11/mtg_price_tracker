"""Filtro estricto local del WooCommerceExtractor (CLAUDE.md #4).

WooCommerce devuelve los nombres con entidades HTML, así que el filtro solo es
correcto si el nombre se desescapa antes de comparar. Nombres reales de cardnexus.cl.
"""
import html
import pytest
from src.extractors.woocommerce import WooCommerceExtractor


def coincide(carta: str, nombre_api: str) -> bool:
    """Replica el pre-proceso que hace _fetch_single_card sobre 'name'."""
    return WooCommerceExtractor._nombre_coincide(carta, html.unescape(nombre_api))


@pytest.mark.parametrize("carta, nombre_api", [
    ("Defile", "Defile"),
    ("Inventors' Fair", "Inventors&#8217; Fair"),
    ("R&D's Secret Lair", "R&amp;D&#8217;s Secret Lair"),
    ("Delver of Secrets", "Delver of Secrets // Insectile Aberration"),
])
def test_acepta_la_carta_correcta(carta, nombre_api):
    assert coincide(carta, nombre_api) is True


@pytest.mark.parametrize("carta, nombre_api", [
    # Homónimos que devolvía el buscador de WooCommerce al pedir 'Defile'
    ("Defile", "Chaos Defiler"),
    ("Defile", "Defiler of Flesh"),
    ("Defile", "Defiler of Vigor"),
    ("Defile", "Defiler of Dreams"),
    ("Defile", "Defiler of Faith"),
    ("Defile", "Defiler of Instinct"),
    ("Inventors", "Inventors&#8217; Fair"),
])
def test_rechaza_homonimos_y_parciales(carta, nombre_api):
    assert coincide(carta, nombre_api) is False
