"""Parseo y filtro estricto del JumpsellerExtractor (CLAUDE.md #6).

Los títulos, SKUs y bloques HTML son ejemplos reales de magic4ever.cl y gamequest.cl,
las dos tiendas Jumpseller del sistema.
"""
import pytest
from src.extractors.jumpseller import JumpsellerExtractor

descomponer = JumpsellerExtractor._descomponer_titulo
coincide = JumpsellerExtractor._nombre_coincide


# ---------- Precios ----------

@pytest.mark.parametrize("texto, esperado", [
    ("$2.000", 2000.0),
    ("$600", 600.0),
    ("$138.000", 138000.0),
    ("desde", None),
    ("", None),
])
def test_parseo_de_precio_en_formato_chileno(texto, esperado):
    assert JumpsellerExtractor._parsear_precio(texto) == esperado


# ---------- Descomposición del título ----------

def test_titulo_de_gamequest_con_atributos_en_pipes():
    info = descomponer("Sol Ring | Inglés | NM | 40K", "40K250NENNM")
    assert info == {
        "nombre": "Sol Ring", "idioma": "Inglés", "estado": "NM",
        "edicion": "40K", "acabado": "No Foil", "variante": "",
    }


def test_titulo_de_gamequest_con_tratamiento_y_foil():
    info = descomponer("Sol Ring (Borderless foil) | Inglés | NM | PIP", "PIP359FENNM")
    assert info["nombre"] == "Sol Ring"
    assert info["acabado"] == "Foil"
    assert info["variante"] == "Borderless"
    assert info["edicion"] == "PIP"


def test_titulo_de_magic4ever_toma_la_edicion_del_sku():
    info = descomponer("Sol Ring", "M-C19-0221")
    assert info["nombre"] == "Sol Ring"
    assert info["edicion"] == "C19"
    assert info["idioma"] == "Inglés"   # magic4ever no declara idioma: se asume inglés
    assert info["estado"] == "NM"


@pytest.mark.parametrize("sku, edicion", [
    ("M-C19-0221", "C19"),
    ("M-40K-0249★", "40K"),        # Tratamiento especial marcado con estrella
    ("M-STX-0246PP", "STX"),       # Promo Pack
    ("M-DTK-0001TL", "DTK"),       # The List
    ("M-BFZ-0087PR", "BFZ"),       # Prerelease
    ("SIN-FORMATO", ""),
])
def test_edicion_desde_el_sku_admite_sufijos_de_tratamiento(sku, edicion):
    assert descomponer("Sol Ring", sku)["edicion"] == edicion


@pytest.mark.parametrize("estado_tienda, esperado", [
    ("NM", "NM"), ("EX", "LP"), ("VG", "MP"), ("HP", "HP"),
])
def test_escala_de_condicion_se_traduce_a_la_del_proyecto(estado_tienda, esperado):
    assert descomponer(f"Fog | Inglés | {estado_tienda} | M12", "")["estado"] == esperado


@pytest.mark.parametrize("idioma_tienda, esperado", [
    ("Inglés", "Inglés"), ("Español", "Español"), ("Japonés", "Japonés"),
])
def test_idioma_se_emite_como_palabra_para_que_lo_lea_el_parser(idioma_tienda, esperado):
    assert descomponer(f"Fog | {idioma_tienda} | NM | M12", "")["idioma"] == esperado


def test_titulo_armado_es_compatible_con_el_parser_del_pipeline():
    from src.utils.parsers import parsear_atributos_carta

    info = descomponer("Sol Ring (Borderless foil) | Español | EX | PIP", "PIP359FESNM")
    atributos = parsear_atributos_carta(JumpsellerExtractor._armar_titulo(info))

    assert atributos["edicion"] == "PIP"
    assert atributos["idioma"] == "ES"
    assert atributos["estado"] == "LP"
    assert atributos["acabado"] == "Foil"
    assert "Borderless" in atributos["variantes"]


# ---------- Filtro estricto ----------

@pytest.mark.parametrize("carta, titulo, sku", [
    ("Sol Ring", "Sol Ring", "M-C19-0221"),
    ("Sol Ring", "Sol Ring | Inglés | NM | 40K", "40K250NENNM"),
    ("Sol Ring", "Sol Ring (Borderless foil) | Inglés | NM | PIP", "PIP359FENNM"),
    ("Fog", "Fog | Inglés | NM | M12", "M12173NENNM"),
    ("Fog", "Fog", "M-M14-0171"),
])
def test_acepta_la_carta_correcta(carta, titulo, sku):
    assert coincide(carta, descomponer(titulo, sku)["nombre"]) is True


@pytest.mark.parametrize("carta, titulo, sku", [
    # El buscador de Jumpseller hace OR entre palabras y devuelve homónimos
    ("Fog", "Fogwalker", "M-EMN-0060"),
    ("Fog", "Fogwell's Gym", "M-MSC-0754"),
    ("Fog", "Foggy Bottom Swamp | Inglés | NM | TLA", "TLA269NENNM"),
    ("Greed", "Greedy Freebooter", "M-LCI-0109"),
    ("Greed", "Devouring Greed", "M-MM2-0078"),
    ("Greed", "Treacherous Greed | Inglés | NM | MKM", ""),
    ("Sol Ring", "Barbarian Ring", "M-JUD-0135"),
    ("Sol Ring", "The Ten Rings", "M-MSC-0001"),
    ("Ugin", "Sanctum of Ugin | Español | NM | BFZ", ""),
    ("Ugin", "Ugin, the Ineffable", "M-WAR-0002"),
    # La edición del título no debe validar la carta
    ("PIP", "Sol Ring (Borderless foil) | Inglés | NM | PIP", "PIP359FENNM"),
])
def test_rechaza_homonimos_y_parciales(carta, titulo, sku):
    assert coincide(carta, descomponer(titulo, sku)["nombre"]) is False


# ---------- Parseo del listado HTML ----------

HTML_LISTADO = """
<article class="theme-block product-block">
  <div class="product-block__labels">
    <div class="product-block__label product-block__label--status">Agotado</div>
  </div>
  <span class="product-block__sku">M-C19-0221</span>
  <h2 class="product-block__title">
    <a href="/sol-ring-25" class="product-block__name">Sol Ring</a>
  </h2>
  <div class="product-block__pricing">
    <div class="product-block__price">$2.000</div>
  </div>
</article>
<article class="theme-block product-block">
  <span class="product-block__sku">M-M14-0171</span>
  <a href="/fog" class="product-block__name">Fog</a>
  <div class="product-block__pricing">
    <div class="product-block__price-wrapper">
      <div class="product-block__price product-block__price--text">desde</div>
      <div class="product-block__price">$450</div>
    </div>
    <div class="product-block__price-wrapper">
      <div class="product-block__price product-block__price--text">hasta</div>
      <div class="product-block__price">$550</div>
    </div>
  </div>
</article>
"""


def test_extrae_los_bloques_del_listado():
    bloques = JumpsellerExtractor._extraer_bloques(HTML_LISTADO)
    assert len(bloques) == 2

    agotado, con_variantes = bloques
    assert agotado["titulo"] == "Sol Ring"
    assert agotado["precio"] == 2000.0
    assert agotado["sku"] == "M-C19-0221"
    assert agotado["etiqueta_estado"] == "Agotado"

    # Con variantes toma el precio mínimo ("desde"), nunca la palabra "desde"
    assert con_variantes["titulo"] == "Fog"
    assert con_variantes["precio"] == 450.0
    assert con_variantes["etiqueta_estado"] == ""
