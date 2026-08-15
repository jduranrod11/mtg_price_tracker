"""
Módulo de Base de Datos.
Centraliza los modelos y la gestión de sesiones.
"""
from .models import Base, Tienda, Carta, HistorialPrecio
from .session import engine, SessionLocal, get_session