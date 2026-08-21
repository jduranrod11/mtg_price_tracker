"""Filtro estricto local del CatLotusExtractor (CLAUDE.md #4).

Los nombres usados son ejemplos reales devueltos por https://catlotus.cl/api/cards,
cuyo buscador interno responde por subcadena (buscar 'Defile' trae 'Dread Defiler').
"""
import pytest
from src.extractors.catlotus import CatLotusExtractor

coincide = CatLotusExtractor._nombre_coincide


@pytest.mark.parametrize("carta, nombre_db", [
    ("Defile", "Defile"),
    ("Sol Ring", "Sol Ring"),
    # Insensible a mayúsculas y a espacios sobrantes
    ("sol ring", "Sol Ring"),
    ("Sol Ring", "  Sol  Ring  "),
    # Apóstrofes tipográficos y acentos
    ("Inventors' Fair", "Inventors’ Fair"),
    ("Lim-Dul's Vault", "Lim-Dûl’s Vault"),
    ("Lim-Dûl's Vault", "Lim-Dul's Vault"),
    # Cartas split / doble cara: cualquiera de las dos caras valida
    ("Delver of Secrets", "Delver of Secrets // Insectile Aberration"),
    ("Insectile Aberration", "Delver of Secrets // Insectile Aberration"),
    ("Wear // Tear", "Wear // Tear"),
    ("Wear", "Wear // Tear"),
    ("Burglar's Plot", "Bilbo, Luckwearer // Burglar’s Plot"),
])
def test_acepta_la_carta_correcta(carta, nombre_db):
    assert coincide(carta, nombre_db) is True


@pytest.mark.parametrize("carta, nombre_db", [
    # El bug reportado: 'Defile' a $500 que en realidad era 'Dread Defiler'
    ("Defile", "Dread Defiler"),
    ("Defile", "Defiler of Flesh"),
    ("Defile", "Defiler of Dreams"),
    ("Defile", "Defiler of Vigor"),
    ("Defile", "Balthor the Defiled"),
    ("Defile", "Chaos Defiler"),
    ("Defile", "Ulamog, the Defiler"),
    # Otros homónimos por subcadena que devuelve la API
    ("Fire", "Balefire Dragon"),
    ("Fire", "Braid of Fire"),
    ("Wear", "Lazav, Wearer of Faces"),
    ("Wear", "Pre-War Formalwear"),
    ("Assault", "Aggravated Assault"),
    ("Cadaver Lab", "Cadaverous Knight"),
    # No basta con ser una subcadena de una cara del split
    ("Delver", "Delver of Secrets // Insectile Aberration"),
    # Nombre más largo que el de la tienda
    ("Sol Ring of Doom", "Sol Ring"),
    # Bordes
    ("", "Defile"),
    ("Defile", ""),
])
def test_rechaza_homonimos_y_parciales(carta, nombre_db):
    assert coincide(carta, nombre_db) is False


# ---------- Idioma ----------

@pytest.mark.parametrize("idioma_api, palabra, codigo", [
    ("eng", "Inglés", "EN"),
    ("esp", "Español", "ES"),
    ("spa", "Español", "ES"),
    ("jpn", "Japonés", "JP"),
    ("zho", "Chino", "CN"),
    ("", "Inglés", "EN"),
])
def test_idioma_se_emite_como_palabra_y_el_parser_lo_reconoce(idioma_api, palabra, codigo):
    """El parser detecta el idioma por la palabra completa, no por el código.

    Emitir "ES" hacía que todas las cartas en español de Cat Lotus se guardaran
    como inglesas (457 filas EN y 0 ES en la última corrida antes del arreglo).
    """
    from src.utils.parsers import parsear_atributos_carta

    assert CatLotusExtractor._traducir_idioma(idioma_api) == palabra

    titulo = f"Sol Ring [3rd Edition] - {palabra} NM No Foil #269"
    assert parsear_atributos_carta(titulo)["idioma"] == codigo
