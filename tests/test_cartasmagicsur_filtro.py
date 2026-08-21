"""Parseo del catálogo de cartasmagicsur.cl.

El HTML es una reducción del listado real de `/catalogo?page=N`: la tarjeta trae
el nombre y la expansión en el `alt` de la imagen, el idioma y la condición en un
badge, y el precio como texto suelto.
"""
import pytest
from src.extractors.cartasmagicsur import CartasMagicsurExtractor

extraer = CartasMagicsurExtractor._extraer_productos


TARJETA = """
<a href="/carta/{href}">
  <div><img alt="{alt}"/></div>
  <div>
    <span>{badge}</span>
    <span>{precio}</span>
  </div>
</a>
"""


def _listado(*tarjetas: dict) -> str:
    return "".join(TARJETA.format(**t) for t in tarjetas)


def test_extrae_nombre_edicion_precio_idioma_y_condicion():
    html = _listado({
        "href": "bfz-242-sanctum-of-ugin?finish=Non-Foil",
        "alt": "Sanctum of Ugin (BFZ)", "badge": "ES · NM", "precio": "$2.170",
    })
    assert extraer(html) == [{
        "nombre": "Sanctum of Ugin", "edicion": "BFZ", "acabado": "No Foil",
        "idioma": "Español", "estado": "NM", "precio": 2170.0,
    }]


def test_detecta_el_acabado_foil_del_alt():
    producto = extraer(_listado({
        "href": "hoc-57-reprieve?finish=Foil",
        "alt": "Reprieve (HOC) Foil", "badge": "EN · NM", "precio": "$79.990",
    }))[0]
    assert producto["acabado"] == "Foil"
    assert producto["nombre"] == "Reprieve"
    assert producto["precio"] == 79990.0


def test_badge_con_varios_idiomas_toma_el_primero():
    producto = extraer(_listado({
        "href": "ktk-103-bring-low", "alt": "Bring Low (KTK)",
        "badge": "EN +1 · NM", "precio": "$450",
    }))[0]
    assert producto["idioma"] == "Inglés"


@pytest.mark.parametrize("badge, estado", [
    ("EN · NM", "NM"), ("EN · EX", "LP"), ("EN · VG", "MP"), ("EN · HP", "HP"),
])
def test_escala_de_condicion_se_traduce_a_la_del_proyecto(badge, estado):
    producto = extraer(_listado({
        "href": "x", "alt": "Fog (M12)", "badge": badge, "precio": "$500",
    }))[0]
    assert producto["estado"] == estado


def test_descarta_tarjetas_sin_precio_publicado():
    html = _listado({"href": "x", "alt": "Sol Ring (C19)", "badge": "EN · NM", "precio": "Sin stock"})
    assert extraer(html) == []


def test_titulo_armado_es_compatible_con_el_parser_del_pipeline():
    from src.utils.parsers import parsear_atributos_carta

    producto = extraer(_listado({
        "href": "sld-1122-ulamog", "alt": "Ulamog, the Ceaseless Hunger (SLD) Foil",
        "badge": "ES · EX", "precio": "$24.990",
    }))[0]
    atributos = parsear_atributos_carta(CartasMagicsurExtractor._armar_titulo(producto))

    assert atributos["edicion"] == "SLD"
    assert atributos["idioma"] == "ES"
    assert atributos["estado"] == "LP"
    assert atributos["acabado"] == "Foil"


# ---------- Filtro estricto ----------

@pytest.mark.parametrize("carta, publicado, esperado", [
    ("Defile", "Defile", True),
    ("Defiled Crypt", "Defiled Crypt // Cadaver Lab", True),   # Vale cualquiera de las caras
    ("Solemn Simulacrum", "Solemn Simulacrum", True),
    # El buscador filtra por subcadena, así que devuelve homónimos
    ("Defile", "Defiled Crypt // Cadaver Lab", False),
    ("Solemn Simulacrum", "Simulacrum Synthesizer", False),
    ("Solemn Simulacrum", "Solemn Offering", False),
    ("Sol Ring", "Sol'Kanar the Tainted", False),
    ("Ugin", "Sanctum of Ugin", False),
    ("Ugin", "Eye of Ugin", False),
    ("Wastes", "Reclaim the Wastes", False),
    ("Wastes", "Encroaching Wastes", False),
])
def test_solo_acepta_coincidencias_exactas(carta, publicado, esperado):
    assert CartasMagicsurExtractor._nombre_coincide(carta, publicado) is esperado
