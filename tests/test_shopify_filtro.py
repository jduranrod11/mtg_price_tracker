"""Filtro estricto local del ShopifyExtractor (CLAUDE.md #4).

Los títulos usados son ejemplos reales de reino-eldrazi.cl, oasisgames.cl y
paytowin.cl, que son las tiendas atendidas por este extractor.
"""
import pytest
from src.extractors.shopify import ShopifyExtractor

coincide = ShopifyExtractor._titulo_coincide


@pytest.mark.parametrize("carta, titulo", [
    # Formato reino-eldrazi: Nombre (SET-###) - Edición [Foil]
    ("Defile", "Defile (DKA-063) - Dark Ascension"),
    ("Defile", "Defile (DKA-063) - Dark Ascension Foil"),
    # Formato oasisgames / paytowin: Nombre [Edición]
    ("Defile", "Defile [Dark Ascension]"),
    ("Sol Ring", "Sol Ring [Commander 2021]"),
    # Tratamientos entre paréntesis antes de la edición
    ("Sol Ring", "Sol Ring (Borderless Alternate Art) [Commander Masters]"),
    ("Ulamog, the Defiler", "Ulamog, the Defiler (Borderless) (MH3-383) - Modern Horizons 3 (Borderless) Foil"),
    # Insensible a mayúsculas (la tienda tiene el typo "Sol RIng")
    ("Sol Ring", "Sol RIng [Foundations]"),
    # Apóstrofes tipográficos y acentos
    ("Inventors' Fair", "Inventors’ Fair [Kaladesh]"),
    ("Lim-Dul's Vault", "Lim-Dûl’s Vault [Alliances]"),
    # Cartas split/dobles: cualquiera de las caras es válida
    ("Defiled Crypt", "Defiled Crypt // Cadaver Lab (DSK-091) - Duskmourn: House of Horror"),
    ("Cadaver Lab", "Defiled Crypt // Cadaver Lab (DSK-091) - Duskmourn: House of Horror Foil"),
    ("Fire // Ice", "Fire // Ice [Apocalypse]"),
    # Acabado pegado al nombre sin separador
    ("Defile", "Defile Foil"),
    ("Defile", "Defile"),
    # Nombres con puntuación interna
    ("H.E.R.B.I.E., Lovable Robot", "H.E.R.B.I.E., Lovable Robot (Extended Art) [Marvel]"),
])
def test_acepta_la_carta_correcta(carta, titulo):
    assert coincide(carta, titulo) is True


@pytest.mark.parametrize("carta, titulo", [
    # El bug original: subcadenas de nombres cortos
    ("Defile", "Defiler of Flesh (DMU-090) - Dominaria United"),
    ("Defile", "Defiler of Flesh (Promo Pack) [Dominaria United Promos]"),
    ("Defile", "Depth Defiler (MH3-058) - Modern Horizons 3: (devoid) Foil"),
    ("Defile", "Ulamog, the Defiler (Borderless) (MH3-383) - Modern Horizons 3 (Borderless) Foil"),
    ("Defile", "Defiled Crypt // Cadaver Lab (DSK-091) - Duskmourn: House of Horror"),
    ("Defile", "Defiling Daemogoth (Extended Art) (SOC-075) - Commander: Secrets of Strixhaven"),
    ("Defile", "Niko Defies Destiny (KHM-226) - Kaldheim"),
    ("Defile", "Balthor the Defiled [Judgment]"),
    ("Fire", "Battle of Frost and Fire (KHM-204) - Kaldheim"),
    ("Fire", "Fire Giant's Fury (KHM-389) - Kaldheim"),
    ("Ulamog", "Spawnsire of Ulamog (ROE-011) - Rise of the Eldrazi"),
    ("Ulamog", "Ulamog, the Ceaseless Hunger (SLD-1122) - Secret Lair Drop (Borderless)"),
    # Hay ediciones que se llaman igual que una carta: solo vale el nombre
    # declarado al inicio del título, no los segmentos de edición.
    ("Apocalypse", "Fire // Ice [Apocalypse]"),
    ("Modern Horizons 3", "Depth Defiler (MH3-058) - Modern Horizons 3: (devoid) Foil"),
    # No debe calzar contra la edición ni el código de set
    ("Kaldheim", "Fire Sages (TLA-136) - Avatar: The Last Airbender"),
    # Nombre más largo que el título
    ("Sol Ring of Doom", "Sol Ring [Fallout]"),
    # Bordes
    ("", "Defile [Dark Ascension]"),
    ("Defile", ""),
])
def test_rechaza_homonimos_y_parciales(carta, titulo):
    assert coincide(carta, titulo) is False
