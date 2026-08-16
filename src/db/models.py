from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Tienda(Base):
    __tablename__ = 'dim_tiendas'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String, unique=True, nullable=False)
    url_base = Column(String, nullable=False)

class Carta(Base):
    __tablename__ = 'dim_cartas'
    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String, unique=True, nullable=False)
    mazo = Column(String, nullable=True)
    edicion_preferida = Column(String, nullable=True)

class HistorialPrecio(Base):
    __tablename__ = 'fact_precios'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ejecucion_id = Column(String, index=True, nullable=False)
    carta_id = Column(Integer, ForeignKey('dim_cartas.id'), nullable=False)
    tienda_id = Column(Integer, ForeignKey('dim_tiendas.id'), nullable=False)
    
    # Columnas normalizadas
    edicion = Column(String)
    idioma = Column(String(2))
    acabado = Column(String(10))
    estado = Column(String(10))
    variantes = Column(String)
    
    precio_clp = Column(Float, nullable=False)
    fecha_extraccion = Column(DateTime, default=datetime.utcnow)

    # Relaciones ORM
    carta = relationship("Carta")
    tienda = relationship("Tienda")