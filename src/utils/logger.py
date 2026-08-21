import logging
import sys

def get_logger(name: str) -> logging.Logger:
    """Configura y retorna un logger estandarizado para el proyecto."""
    logger = logging.getLogger(name)

    # Evitar agregar handlers múltiples si el logger ya fue instanciado
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        # Formato del log: [Fecha/Hora] [Nivel] [Módulo] - Mensaje
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # En Windows, la consola suele quedar en cp1252 y revienta al loguear
        # emojis (ej. los indicadores 🟢🟡🔴 de "Dólar Efectivo"). Forzamos UTF-8.
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")

        # Handler para la consola
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        
        # Handler para el archivo físico
        file_handler = logging.FileHandler("tracker.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        
    return logger