# MTG Price Tracker - Guía de Proyecto y Reglas de Arquitectura

## Contexto del Proyecto
Sistema de extracción y analítica de precios del mercado secundario de cartas de Magic: The Gathering.
Rastrea precios en tiendas locales (Chile, en CLP) y los compara contra un benchmark internacional
(Card Kingdom, en USD) para detectar oportunidades de compra mediante el indicador **"Dólar Efectivo"**:
cuántos pesos se están pagando por cada dólar de valor de mercado de la carta.

Flujo completo: `main.py` (extracción → carga) → `fact_precios` → `src/analytics/dolar_efectivo.py`
(única fuente de la lógica de negocio) → `dashboard.py` y `reporte_oportunidades.py`.

## Comandos
Todo se ejecuta con `uv` (nunca `python` ni `pip` directo):

```bash
uv run main.py                        # Pipeline completo: extracción, carga y reporte del día
uv run streamlit run dashboard.py     # Dashboard
uv run reporte_oportunidades.py       # Solo el reporte Markdown, sobre los datos ya cargados
uv run pytest -q                      # Suite completa (rápida, sin red)
uv run alembic upgrade head           # Migraciones de esquema
```

## Mapa del repositorio
| Ruta | Rol |
|---|---|
| `main.py` | Orquestación del pipeline y catálogo de cartas objetivo |
| `src/config.py` | Parámetros globales del negocio (tasa de cambio) |
| `src/extractors/base.py` | Clase base: red, reintentos, normalización y filtro de nombres |
| `src/extractors/*.py` | Un extractor por tecnología de tienda + `factory.py` |
| `src/db/` | Modelos SQLAlchemy (esquema en estrella) y sesión |
| `src/analytics/dolar_efectivo.py` | Lógica de negocio del Dólar Efectivo (fuente única) |
| `src/utils/parsers.py` | Extracción de edición/idioma/acabado/estado desde el título de tienda |
| `migrations/` | Alembic: dueño del esquema |
| `tests/` | Pruebas de los filtros y del cálculo de negocio |

## Stack Tecnológico
* **Lenguaje:** Python 3.13+
* **Gestor de Paquetes/Entorno:** `uv` (los comandos se ejecutan con `uv run ...`)
* **Extracción de Datos:** `httpx` (asíncrono) y `asyncio`; `BeautifulSoup` solo para las
  tiendas que no exponen API (Jumpseller)
* **Base de Datos:** SQLite vía `SQLAlchemy`, esquema en estrella (`fact_precios`, `dim_cartas`, `dim_tiendas`)
* **Migraciones:** `Alembic`
* **Frontend / Dashboard:** `Streamlit` (`pandas`, `numpy`)
* **Pruebas:** `pytest`

Las dependencias declaradas en `pyproject.toml` deben coincidir con lo que realmente se importa:
si agregas un import, decláralo; si eliminas el último uso de un paquete, sácalo.

## Arquitectura de Extractores (`src/extractors/`)

1. **Patrón Factory:** todos los extractores se instancian a través de `ExtractorFactory`
   (`factory.py`) según el dominio de la tienda. Agregar una tienda es agregarla a la lista
   del dominio correspondiente, no crear una rama nueva en el pipeline.

2. **Herencia obligatoria de `BaseExtractor`:** cada extractor implementa únicamente
   `_fetch_single_card()`. Los reintentos, headers, concurrencia ("tiendas en paralelo /
   cartas en serie") y la construcción del resultado ya están resueltos en la base y no se
   reimplementan por tienda.

3. **Asincronía pura:** toda extracción de red es `async` con `httpx.AsyncClient`.
   **NO** usar Selenium, Playwright ni peticiones síncronas (`requests`) en el backend de
   extracción. (`requests` sí está permitido en `dashboard.py` para consultar Scryfall.)

4. **Configuración de red anti-Cloudflare (no modificar sin medir):**
   * `BaseExtractor.HTTP2 = False`. El handshake HTTP/2 de httpx delata el TLS fingerprint
     del cliente Python y las tiendas Shopify responden **403**. Forzar HTTP/1.1 los elimina.
     No reactivar `http2=True` "para ir más rápido".
   * `BaseExtractor.DEFAULT_HEADERS` simula un Chrome 124 completo (`User-Agent` con
     `KHTML, like Gecko`, `sec-ch-ua*`, `sec-fetch-*`). Los headers deben ser coherentes
     entre sí: un `User-Agent` de Chrome sin sus `sec-ch-ua` es una firma de bot.

5. **Manejo de bloqueos (429/403):** siempre *Exponential Backoff* (`_get_with_retry`) y
   pausas de cortesía (`asyncio.sleep(self.delay)`) entre cartas y entre páginas.
   Delays vigentes: Shopify 1.5 s, WooCommerce 2.0 s, Cat Lotus 2.0 s, Jumpseller 2.0 s,
   cartasmagicsur 2.0 s.

6. **Búsqueda Amplia + filtro estricto local:** los buscadores internos de las tiendas fallan
   con apóstrofes y comas, así que la consulta a la API se hace con la **raíz** del nombre
   (`re.split(r"[',\/]", carta_nombre)[0]` o equivalente) para traer de más, y **el descarte
   se hace en Python**.

### Tiendas y plataformas

| Plataforma | Tiendas | Fuente de datos |
|---|---|---|
| Shopify | oasisgames, paytowin, reino-eldrazi | `/search/suggest.json` + `/products/{handle}.js` |
| WooCommerce | cardnexus, huntercardtcg, rhysticbazaar, lacripta | `/wp-json/wc/store/products` |
| Cat Lotus | catlotus | API nativa `/api/cards` (paginada) |
| Jumpseller | magic4ever, gamequest | HTML de `/search?q=` |
| A medida (Next.js) | cartasmagicsur | HTML de `/catalogo?q=` (subcadena sobre el nombre) |
| Card Kingdom | cardkingdom | `ck_pricelist_cache.json` (ver Reglas de Negocio #1) |

**cartasmagicsur** tiene dos caminos muertos que conviene no volver a explorar. Su backend
es Supabase, pero el cliente nunca consulta las cartas desde ahí (solo `customers`, `sets`
y `events_public_view`) y su `robots.txt` declara `Disallow: /api/`: llegar a los precios
por esa vía exigiría enumerar su esquema, y queda descartado. La ficha
`/carta/{set}-{n}-{slug}` tampoco sirve, porque renderiza en el servidor solo las
recomendaciones del pie — el precio del producto principal lo pide el navegador después.
Y recorrer `/catalogo?page=N` sin `q` **parece** traer el catálogo completo (termina cerca
de la página 101), pero está truncado y omite cartas con stock: `Solemn Simulacrum (TSR)`,
`Skullclamp (FIC)` y `Feign Death (AFR)` aparecen en el buscador y no en ese recorrido.
Lo que sí funciona es `/catalogo?q=`, que filtra por **subcadena sobre el nombre** y lista
solo lo que hay en stock: se consulta carta por carta con la raíz del nombre, se pagina de
a 12 y se filtra localmente, como el resto de las tiendas.

Jumpseller no tiene API pública de storefront: `/api/products` exige credenciales de
administrador y no existe `/products.json`, así que se parsea el HTML del listado con
BeautifulSoup. Su buscador hace **OR** entre las palabras ("Sol Ring" devuelve 120 páginas
de cualquier cosa con "sol" o "ring"), pero ordena por relevancia y agrupa las coincidencias
exactas al principio: por eso se pagina mientras la página aporte coincidencias y se corta
en la primera que no aporte ninguna. Los precios vienen ya formateados en pesos
(`$2.000`), nunca en centésimas.

### Regla crítica del filtro local: igualdad exacta, jamás subcadena

El filtro **nunca** puede ser `if carta in nombre_tienda`. Esa comparación hace que "Defile"
calce con `Dread Defiler`, `Defiler of Flesh`, `Depth Defiler` y `Ulamog, the Defiler`, y
contamina el Dólar Efectivo con precios de cartas que no son la buscada (un `Dread Defiler`
a $500 aparece como un "Defile a $500" que no existe).

Usar siempre uno de los dos helpers, según lo que exponga la API de la tienda:

| Helper | Cuándo | Qué hace |
|---|---|---|
| `BaseExtractor._nombre_coincide()` | La API expone el nombre de carta limpio (Cat Lotus, WooCommerce) | Igualdad exacta del nombre normalizado |
| `ShopifyExtractor._titulo_coincide()` | El título trae la edición anexada (`Defile (DKA-063) - Dark Ascension`) | Compara contra el primer segmento, antes del paréntesis/corchete de edición |

Ambos normalizan igual antes de comparar: minúsculas, sin acentos (NFKD), apóstrofes
tipográficos unificados (`’` → `'`) y espacios colapsados.

Cuando la tienda anexa los atributos al nombre con un separador propio, el extractor los
descompone primero en campos y recién entonces compara el nombre con `_nombre_coincide`:
Jumpseller usa pipes (`Sol Ring (Borderless foil) | Inglés | NM | PIP`) y rhysticbazaar
raya y punto medio (`Sol Ring — Near Mint · Spanish`). Nunca se compara contra el título
completo.

Detalles que el filtro debe respetar:
* **Cartas dobles y split:** las tiendas las guardan como `Cara A // Cara B`. Buscar
  cualquiera de las dos caras debe validar la carta.
* **Solo el primer segmento en Shopify:** hay ediciones que se llaman igual que una carta
  (`Fire // Ice [Apocalypse]` no debe validar la carta `Apocalypse`).
* **Entidades HTML:** WooCommerce devuelve `Inventors&#8217; Fair` y `R&amp;D's Secret Lair`.
  Desescapar con `html.unescape()` **antes** de comparar.
* **Descartes al log:** cada rechazo se registra con `logger.debug`, para poder auditar por
  qué una carta no apareció.

Todo filtro nuevo o modificado llega con casos de prueba en `tests/`, usando **títulos reales**
copiados de la API de la tienda (aciertos y homónimos).

## Reglas de Negocio Críticas (¡NO MODIFICAR SIN AUTORIZACIÓN!)

1. **Card Kingdom (HITL - Human In The Loop):** Card Kingdom tiene protección Cloudflare
   Turnstile extrema. `CardKingdomExtractor` **NO** hace web scraping, ni abre navegadores,
   ni consulta la web de la tienda: resuelve todas las búsquedas contra un índice en RAM
   construido desde `ck_pricelist_cache.json`, que el usuario descarga manualmente.
   La única salida a la red permitida es la API pública oficial de pricelist, y solo cuando
   el caché supera las 12 horas. Esa descarga **falla con 403 con frecuencia**: si el índice
   queda vacío, el pipeline debe abortar ruidosamente, nunca escribir un día entero sin
   benchmark (todas las cartas quedarían en "⚪ Sin Ref." con el run marcado como exitoso).

2. **Asincronía de datos entre tiendas:** las tiendas no se actualizan al mismo tiempo.
   Las consultas analíticas deben buscar la última `ejecucion_id` **de cada tienda por
   separado** (`GROUP BY tienda_id`), nunca una ejecución global.
   *Consecuencia a vigilar:* un run parcial (una tienda que respondió a medias) se convierte
   en "lo vigente" de esa tienda y las cartas faltantes desaparecen del dashboard sin aviso.

3. **Tasa de cambio:** el benchmark en USD se convierte a CLP con `TASA_USD_CLP_REFERENCIA`,
   definida **únicamente** en `src/config.py`. No duplicar el literal en extractores,
   dashboard ni reportes. Ten presente que `fact_precios` guarda el precio de Card Kingdom
   **ya convertido a CLP** con la tasa vigente al momento de extraer: cambiar la tasa no
   recalcula el histórico.

4. **Umbrales del Dólar Efectivo:** viven en `src/analytics/dolar_efectivo.py`
   (`UMBRAL_CONVENIENTE`, `UMBRAL_MERCADO`) y son la fuente única para dashboard y reportes.
   Ninguna vista recalcula el indicador por su cuenta.

5. **Imágenes:** las imágenes de las cartas en el dashboard se obtienen en tiempo real desde
   la API pública de Scryfall, cacheadas 24 h con `st.cache_data`.

## Catálogo de cartas y convenciones de nombres
El catálogo objetivo se define en `main.py` (`cartas_target`: nombre de carta → mazo).

* Los nombres se escriben **exactamente como en Scryfall**, que es también como los guardan
  las tiendas.
* Las cartas dobles, transformables y split usan ` // ` (doble barra con espacios), nunca
  ` / `. Un nombre con una sola barra no calza con ninguna tienda y la carta desaparece del
  seguimiento en silencio.
* Para dejar una carta fuera temporalmente, comentar la línea; las anotaciones de compra
  (`GRATIS, VALIDAR RECIBO`) van como comentario al final de esa línea.

## Base de datos y migraciones
* Esquema en estrella: `fact_precios` (hechos) + `dim_cartas` / `dim_tiendas` (dimensiones).
* **Alembic es el dueño del esquema.** Todo cambio de columna o tabla se hace con una
  migración (`uv run alembic revision --autogenerate`), no editando `models.py` a solas.
  `Base.metadata.create_all()` en `main.py` existe solo para inicializar una base nueva.
* Cada corrida escribe un `ejecucion_id` (`YYYYMMDD_HHMMSS`); su orden lexicográfico es el
  cronológico, y de eso depende el `MAX(ejecucion_id)` de las consultas analíticas.
  No cambiar el formato.
* Las marcas de tiempo se guardan en **UTC con zona horaria explícita**
  (`datetime.now(timezone.utc)`, no el deprecado `utcnow()`), y se convierten a hora local
  solo al presentarlas.
* Los precios se normalizan a CLP reales al extraer, usando la unidad que declara cada API
  (`currency_minor_unit` en WooCommerce; Shopify `.js` siempre devuelve centésimas).
  No adivinar la escala a partir del valor.

## Pruebas
* `uv run pytest -q` no toca la red: los extractores se prueban por sus funciones puras
  (filtros de nombre, parseo de atributos) y la analítica con DataFrames construidos a mano.
* Cada bug de datos corregido deja un caso de regresión con el dato real que lo destapó.
* Las verificaciones contra las tiendas reales se hacen a mano, con delays de cortesía, y
  nunca dentro de la suite.

## Estilo de Código y Convenciones
* **Logging:** usar siempre `src.utils.logger`. Nada de `print()` en producción.
  `INFO` para el avance del pipeline, `WARNING` para bloqueos reintentables, `ERROR` para
  fallos definitivos, `DEBUG` para descartes del filtro.
* **Tipado:** Type Hinting en todas las firmas de funciones y métodos.
* **Idioma:** código, variables y comentarios en español, salvo nombres de APIs externas o
  estándares técnicos. Los comentarios explican *por qué*, no *qué*: las decisiones
  anti-bloqueo y las reglas de negocio se documentan en el punto donde viven.
* **Higiene del repositorio:** no versionar artefactos que se regeneran en cada corrida
  (`ck_pricelist_cache.json` de ~65 MB, `mtg_tracker.db`, `tracker.log`, HTML de depuración).
  Van en `.gitignore`.

## Deuda conocida (actualizar al resolverla)
* El catálogo de cartas vive incrustado en `main.py`; el módulo `src/pipeline.py` existe
  vacío, reservado para separar orquestación de configuración.
* La carga a la base hace dos `SELECT` por fila (~19.000 consultas por corrida) en vez de
  precargar las dimensiones en diccionarios.
* `ShopifyExtractor._normalizar` duplica `BaseExtractor._normalizar_nombre`; se mantiene así
  a propósito para no tocar el filtro de Shopify ya validado.
* **huntercardtcg.com responde 200 con lista vacía** para casi toda consulta: su catálogo o
  su buscador están caídos del lado de la tienda. Quedó con 0 filas en la última corrida.
* Card Kingdom sigue descargando la pricelist cuando el caché supera 12 h, y un índice
  vacío no aborta la corrida (ver Reglas de Negocio #1).
* Un run degradado avanza igual el snapshot de esa tienda: falta un chequeo de salud que
  marque la corrida como parcial en vez de dejar desaparecer cartas del dashboard.
