import asyncio
import pandas as pd
import urllib.parse
from datetime import datetime, timezone

from src.db import engine, Base, Tienda, Carta, HistorialPrecio, SessionLocal
from src.extractors.factory import ExtractorFactory
from src.utils.parsers import parsear_atributos_carta
from src.utils.logger import get_logger
from reporte_oportunidades import generar_reporte

logger = get_logger(__name__)

async def ejecutar_todos_los_motores(tiendas_por_extractor, cartas_nombres):
    tareas = []
    for ext_name, ext_data in tiendas_por_extractor.items():
        logger.info(f"Preparando motor {ext_name} para {len(ext_data['urls'])} tiendas...")
        extractor_instancia = ext_data['instancia']
        urls_asignadas = ext_data['urls']

        # Agregamos la ejecución asíncrona a la lista de tareas
        tareas.append(extractor_instancia.extraer_precios_batch(urls_asignadas, cartas_nombres))

    # asyncio.gather ejecuta todas las tareas de la lista simultáneamente
    resultados_agrupados = await asyncio.gather(*tareas)

    # Aplanar la lista de listas
    return [item for sublist in resultados_agrupados for item in sublist]

def main():
    # UTC, igual que `fecha_extraccion`: el orden lexicográfico de este id es el
    # criterio cronológico de las consultas analíticas y con hora local el cambio
    # de horario de verano podría romper la monotonía.
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    logger.info(f"=== INICIANDO PIPELINE MTG TRACKER | RUN ID: {run_id} ===")
    
    # 1. INICIALIZACIÓN DE BASE DE DATOS
    # Solo para arrancar una base nueva: el dueño del esquema es Alembic
    # (`uv run alembic upgrade head`). No sustituye a las migraciones.
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    tiendas_target = [
        "https://www.oasisgames.cl",
        "https://www.paytowin.cl",
        "https://cardnexus.cl",
        # "https://huntercardtcg.com",
        "https://www.catlotus.cl",
        "https://reino-eldrazi.cl",
        "https://www.magic4ever.cl",
        "https://www.cartasmagicsur.cl",
        "https://rhysticbazaar.cl",
        "https://gamequest.cl",
        "https://www.cardkingdom.com"
    ]
    cartas_target = {
        "Akroma's Memorial": "Zhulodok, Void Gorger",
        "All Is Dust": "Zhulodok, Void Gorger",
        "Arch of Orazca": "Zhulodok, Void Gorger",
        "Artisan of Kozilek": "Zhulodok, Void Gorger",
        "Blast Zone": "Zhulodok, Void Gorger",
        "Blasted Landscape": "Zhulodok, Void Gorger",
        "Breaker of Creation": "Zhulodok, Void Gorger",
        "Buried Ruin": "Zhulodok, Void Gorger",
        "Cityscape Leveler": "Zhulodok, Void Gorger",
        "Coldsteel Heart": "Zhulodok, Void Gorger",
        "Darksteel Citadel": "Zhulodok, Void Gorger",
        "Darksteel Monolith": "Zhulodok, Void Gorger",
        "Devourer of Destiny": "Zhulodok, Void Gorger",
        "Eldritch Immunity": "Zhulodok, Void Gorger",
        "Eye of Ugin": "Zhulodok, Void Gorger",
        "Field of Ruin": "Zhulodok, Void Gorger",
        "Forsaken Monument": "Zhulodok, Void Gorger",
        "Fractured Powerstone": "Zhulodok, Void Gorger",
        "H.E.R.B.I.E., Lovable Robot": "Zhulodok, Void Gorger",
        "It That Betrays": "Zhulodok, Void Gorger",
        "Kozilek, the Great Distortion": "Zhulodok, Void Gorger",
        "Manakin": "Zhulodok, Void Gorger",
        "Myr Convert": "Zhulodok, Void Gorger",
        "Page, Loose Leaf": "Zhulodok, Void Gorger",
        "Palladium Myr": "Zhulodok, Void Gorger",
        "Plague Myr": "Zhulodok, Void Gorger",
        "Scavenger Grounds": "Zhulodok, Void Gorger",
        "Solar Transformer": "Zhulodok, Void Gorger",
        "Solemn Simulacrum": "Zhulodok, Void Gorger",
        "Spawnbed Protector": "Zhulodok, Void Gorger",
        "Stonespeaker Crystal": "Zhulodok, Void Gorger",
        "Summon: Bahamut": "Zhulodok, Void Gorger",
        "The Irencrag": "Zhulodok, Void Gorger",
        "Ugin, the Spirit Dragon": "Zhulodok, Void Gorger",
        "Ugin's Labyrinth": "Zhulodok, Void Gorger",
        "Ulamog, the Ceaseless Hunger": "Zhulodok, Void Gorger",
        "Ulamog, the Defiler": "Zhulodok, Void Gorger",
        "Ulamog, the Infinite Gyre": "Zhulodok, Void Gorger",
        "Ultima, Origin of Oblivion": "Zhulodok, Void Gorger",
        "Urza's Cave": "Zhulodok, Void Gorger",
        "Urza's Tower": "Zhulodok, Void Gorger",
        "Vibranium Dynamo": "Zhulodok, Void Gorger",
        "Void Winnower": "Zhulodok, Void Gorger",
        "Volatile Fault": "Zhulodok, Void Gorger",
        "Wastes": "Zhulodok, Void Gorger",
        "Wayfarer's Bauble": "Zhulodok, Void Gorger",
        "Acorn Harvest": "The Unbeatable Squirrel Girl",
        "Avatar Sanctuary": "The Unbeatable Squirrel Girl",
        "Banner of Kinship": "The Unbeatable Squirrel Girl",
        "Beastmaster Ascension": "The Unbeatable Squirrel Girl",
        "Chatter of the Squirrel": "The Unbeatable Squirrel Girl",
        "Chitterspitter": "The Unbeatable Squirrel Girl",
        "Deep Forest Hermit": "The Unbeatable Squirrel Girl",
        "Druid's Call": "The Unbeatable Squirrel Girl",
        "Emerald Medallion": "The Unbeatable Squirrel Girl",
        "Enduring Vitality": "The Unbeatable Squirrel Girl",
        "Essence Warden": "The Unbeatable Squirrel Girl",
        "Firdoch Core": "The Unbeatable Squirrel Girl",
        "Fog": "The Unbeatable Squirrel Girl",
        "Growing Rites of Itlimoc // Itlimoc, Cradle of the Sun": "The Unbeatable Squirrel Girl",
        "Guardian Project": "The Unbeatable Squirrel Girl",
        "Idol of Oblivion": "The Unbeatable Squirrel Girl",
        "Jaheira, Friend of the Forest": "The Unbeatable Squirrel Girl",
        "Mana Reflection": "The Unbeatable Squirrel Girl",
        "Nature's Lore": "The Unbeatable Squirrel Girl",
        "Noxious Newt": "The Unbeatable Squirrel Girl",
        "Ohran Frostfang": "The Unbeatable Squirrel Girl",
        "Patchwork Banner": "The Unbeatable Squirrel Girl",
        "Primal Rage": "The Unbeatable Squirrel Girl",
        "Quest for Renewal": "The Unbeatable Squirrel Girl",
        "Rootcast Apprenticeship": "The Unbeatable Squirrel Girl",
        "Sakura-Tribe Elder": "The Unbeatable Squirrel Girl",
        "Scurrid Colony": "The Unbeatable Squirrel Girl",
        "Scurry of Squirrels": "The Unbeatable Squirrel Girl",
        "Search for Tomorrow": "The Unbeatable Squirrel Girl",
        "Seedborn Muse": "The Unbeatable Squirrel Girl",
        "Selfless Safewright": "The Unbeatable Squirrel Girl",
        "Shamanic Revelation": "The Unbeatable Squirrel Girl",
        "Skullclamp": "The Unbeatable Squirrel Girl",
        "Skyshroud Claim": "The Unbeatable Squirrel Girl",
        "Squirrel Mob": "The Unbeatable Squirrel Girl",
        "Squirrel Sovereign": "The Unbeatable Squirrel Girl",
        "Studious First-Year // Rampant Growth": "The Unbeatable Squirrel Girl",
        "Swarmyard": "The Unbeatable Squirrel Girl",
        "Tippy-Toe, Terrific Partner": "The Unbeatable Squirrel Girl",
        "Tribute to the World Tree": "The Unbeatable Squirrel Girl",
        "Triumph of the Hordes": "The Unbeatable Squirrel Girl",
        "Verdant Command": "The Unbeatable Squirrel Girl",
        "Dark Deal": "Sheoldred, the Apocalypse",
        "Defile": "Sheoldred, the Apocalypse",
        "Elder Brain": "Sheoldred, the Apocalypse",
        "Eldritch Pact": "Sheoldred, the Apocalypse",
        "Erebos, God of the Dead": "Sheoldred, the Apocalypse",
        "Fate Unraveler": "Sheoldred, the Apocalypse",
        "Feed the Swarm": "Sheoldred, the Apocalypse",
        "Feign Death": "Sheoldred, the Apocalypse",
        "Geier Reach Sanitarium": "Sheoldred, the Apocalypse",
        "Gixian Puppeteer": "Sheoldred, the Apocalypse",
        "Greed": "Sheoldred, the Apocalypse",
        "Malakir Rebirth // Malakir Mire": "Sheoldred, the Apocalypse",
        "Marauding Blight-Priest": "Sheoldred, the Apocalypse",
        "Master of the Feast": "Sheoldred, the Apocalypse",
        "Mutilate": "Sheoldred, the Apocalypse",
        "Not Dead After All": "Sheoldred, the Apocalypse",
        "Ob Nixilis, the Hate-Twisted": "Sheoldred, the Apocalypse",
        "Psychosis Crawler": "Sheoldred, the Apocalypse",
        "Rankle, Master of Pranks": "Sheoldred, the Apocalypse",
        "Read the Bones": "Sheoldred, the Apocalypse",
        "Sanguine Bond": "Sheoldred, the Apocalypse",
        "Scrawling Crawler": "Sheoldred, the Apocalypse",
        "Seizan, Perverter of Truth": "Sheoldred, the Apocalypse",
        "Sheoldred's Edict": "Sheoldred, the Apocalypse",
        "Sign in Blood": "Sheoldred, the Apocalypse",
        "Snuff Out": "Sheoldred, the Apocalypse",
        "Undying Malice": "Sheoldred, the Apocalypse",
        "Vito, Thorn of the Dusk Rose": "Sheoldred, the Apocalypse",
        "Witch of the Moors": "Sheoldred, the Apocalypse",
    }

    cartas_nombres = list(cartas_target.keys())

    try:
        logger.info("Sincronizando dimensiones (Tiendas y Cartas) en la BD...")
        for url in tiendas_target:
            if not session.query(Tienda).filter_by(url_base=url).first():
                nombre_limpio = urllib.parse.urlparse(url).netloc.replace('www.', '')
                session.add(Tienda(nombre=nombre_limpio, url_base=url))

        for nombre, mazo in cartas_target.items():
            carta_db = session.query(Carta).filter_by(nombre=nombre).first()
            if not carta_db:
                session.add(Carta(nombre=nombre, mazo=mazo))
            else:
                carta_db.mazo = mazo # Actualiza el mazo por si cambiaste la carta de mazo
        session.commit()

        logger.info("Determinando motor de extracción por tienda...")
        tiendas_por_extractor = {}
                
        for url in tiendas_target:
            extractor = ExtractorFactory.obtener_extractor(url)
            if extractor:
                ext_name = extractor.__class__.__name__
                if ext_name not in tiendas_por_extractor:
                    tiendas_por_extractor[ext_name] = {'instancia': extractor, 'urls': []}
                tiendas_por_extractor[ext_name]['urls'].append(url)
            else:
                logger.warning(f"No hay extractor configurado para la tienda: {url}")

        # --- EXTRACCIÓN GLOBAL ASÍNCRONA ---
        logger.info("Lanzando todos los extractores a la red simultáneamente...")
        datos_extraidos = asyncio.run(ejecutar_todos_los_motores(tiendas_por_extractor, cartas_nombres))

        # 3. TRANSFORMACIÓN Y CARGA
        logger.info("Aplicando transformaciones RegEx y cargando a la base de datos...")
        for registro in datos_extraidos:
            atributos = parsear_atributos_carta(registro['titulo_tienda'])
            
            if atributos['estado'] not in ['NM', 'LP'] or atributos['idioma'] not in ['EN', 'ES']:
                continue
            
            tienda = session.query(Tienda).filter_by(url_base=registro['tienda_url']).first()
            carta = session.query(Carta).filter_by(nombre=registro['carta_nombre']).first()
            
            nuevo_precio = HistorialPrecio(
                ejecucion_id=run_id,
                carta_id=carta.id,
                tienda_id=tienda.id,
                edicion=atributos['edicion'],
                idioma=atributos['idioma'],
                acabado=atributos['acabado'],
                estado=atributos['estado'],
                variantes=atributos['variantes'],
                precio_clp=registro['precio_clp']
            )
            session.add(nuevo_precio)
            
        session.commit()
        logger.info("Carga a la base de datos exitosa.")

        # 4. REPORTE DE OPORTUNIDADES (Dólar Efectivo)
        logger.info("Generando reporte de oportunidades del día...")
        try:
            generar_reporte(engine=engine)
        except Exception as e:
            # Un fallo en el reporte no debe marcar como fallida la extracción/carga.
            logger.error(f"No se pudo generar el reporte de oportunidades: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Fallo crítico en el pipeline: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()
        logger.info("=== PIPELINE FINALIZADO ===")

if __name__ == "__main__":
    main()