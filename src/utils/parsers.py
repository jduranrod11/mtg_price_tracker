import re
import html # <-- IMPORTANTE: Agregamos esta librería nativa

def parsear_atributos_carta(titulo_tienda: str) -> dict:
    # Decodificar entidades HTML (Convierte '&#8211;' en '-')
    titulo_limpio = html.unescape(titulo_tienda)
    titulo_upper = titulo_limpio.upper()
    
    # 1. Extraer Edición
    match_edicion = re.search(r'\[(.*?)\]', titulo_limpio)
    edicion = match_edicion.group(1).strip() if match_edicion else ""
    
    # 2. Extraer Idioma
    idioma = "EN"
    if "ESPAÑOL" in titulo_upper or "SPANISH" in titulo_upper or "/ ES " in titulo_upper:
        idioma = "ES"
    elif "JAPANESE" in titulo_upper or "JAPON" in titulo_upper or "/ JP " in titulo_upper:
        idioma = "JP"
    elif "CHINESE" in titulo_upper or "CHIN" in titulo_upper or "/ CN " in titulo_upper:
        idioma = "CN"
        
    # 3. Identificar Acabado (El orden importa: Primero descartar 'No Foil')
    acabado = "Normal"
    if "NO FOIL" in titulo_upper or "NON FOIL" in titulo_upper or "NON-FOIL" in titulo_upper:
        acabado = "Normal"
    elif "FOIL" in titulo_upper:
        acabado = "Foil"

    # 4. Identificar Estado (Condition)
    estado = "NM" # Default si no se especifica
    if re.search(r'\b(LP|LIGHTLY PLAYED|SLIGHTLY PLAYED|SP)\b', titulo_upper):
        estado = "LP"
    elif re.search(r'\b(MP|MODERATELY PLAYED|PLAYED)\b', titulo_upper):
        estado = "MP"
    elif re.search(r'\b(HP|HEAVILY PLAYED)\b', titulo_upper):
        estado = "HP"
    elif re.search(r'\b(DM|DAMAGED)\b', titulo_upper):
        estado = "DM"
    elif re.search(r'\b(NM|NEAR MINT|MINT|M)\b', titulo_upper):
        estado = "NM"
        
    # 5. Identificar Variantes Especiales
    variantes = []
    if "SHOWCASE" in titulo_upper: variantes.append("Showcase")
    if "TIMESHIFTED" in titulo_upper: variantes.append("Timeshifted")
    if "PROMO" in titulo_upper: variantes.append("Promo")
    if "RETRO" in titulo_upper: variantes.append("Retro")
    if "BORDERLESS" in titulo_upper: variantes.append("Borderless")
    if "EXTENDED ART" in titulo_upper: variantes.append("Extended Art")
    
    # --- NUEVO: Extraer Número de Coleccionista ---
    # Ahora que el HTML está decodificado, el regex encontrará el número real
    match_numero = re.search(r'#\s*\d+', titulo_upper)
    if match_numero:
        variantes.append(match_numero.group(0))
    
    return {
        "edicion": edicion,
        "idioma": idioma,
        "acabado": acabado,
        "estado": estado,
        "variantes": ", ".join(variantes) if variantes else "Normal"
    }