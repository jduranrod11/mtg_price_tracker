"""
Configuración global del proyecto.

Único lugar donde se parametriza la tasa de cambio USD/CLP usada como
referencia (CLAUDE.md, Reglas de Negocio Críticas #3). Antes vivía
duplicada como literal `800` en `src/extractors/factory.py`,
`src/extractors/cardkingdom.py` y `dashboard.py` — quedar desincronizada
en una de esas copias cambiaría silenciosamente el benchmark de "Dólar
Efectivo" en unos lugares sí y en otros no.
"""

TASA_USD_CLP_REFERENCIA: int = 800
