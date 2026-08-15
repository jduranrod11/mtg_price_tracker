from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base

# Configuración por defecto usando SQLite para pruebas iniciales.
# Cuando quieras apuntar a tu SQL Server local o productivo, 
# simplemente cambia esta cadena por tu conexión mssql+pyodbc.
DB_URL = "sqlite:///mtg_tracker.db"

# Creación del motor
engine = create_engine(DB_URL, echo=False)

# Fábrica de sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_session():
    """
    Generador que provee una sesión de base de datos.
    Asegura que la sesión se cierre (y se libere la conexión) al terminar.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()