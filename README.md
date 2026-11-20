# MUSEO — Servicio de IA

[![CI](https://github.com/Luisaparrac/BarnizGallery-IA/actions/workflows/ci.yml/badge.svg)](https://github.com/Luisaparrac/BarnizGallery-IA/actions/workflows/ci.yml)

Servicio de inteligencia artificial de **MUSEO**, la galería 3D y tienda del Barniz de Pasto
Mopa-Mopa. Proyecto final del curso *Patrones de Software* (Universidad Cooperativa de Colombia).

- Solo lo llama el backend; el frontend nunca habla con este servicio.
- No tiene estado ni base de datos: recibe en el JSON lo que necesita y responde.
- Todas las rutas, menos `/health`, piden el header `X-API-Key: <AI_SERVICE_KEY>`.
- Los errores tienen siempre la forma `{"code": "...", "message": "..."}`.

## Arquitectura

```mermaid
flowchart LR
    FE["Frontend 3D"] --> BE["Backend Spring<br/>AiServiceGateway"]
    BE -- "HTTPS + X-API-Key" --> MW

    subgraph IA["Servicio de IA (FastAPI)"]
        MW["Middlewares<br/>X-Request-ID · logs JSON · tamaño máximo"] --> SEC["Límite por minuto<br/>+ API key"]
        SEC --> R1["/v1/designs"]
        SEC --> R2["/v1/recommendations"]
        SEC --> R3["/v1/pricing/suggest"]
        SEC --> R4["/v1/metrics"]

        R1 --> DS["DesignService<br/>(Facade)"]
        DS --> MOD["ContentModerator<br/>(Adapter)"]
        DS --> BUD["DailyImageBudget"]
        DS --> PB["DesignPromptBuilder<br/>(Builder)"]
        DS --> F["ImageProviderFactory<br/>(Factory Method)"]
        F --> FAKE["FakeImageProvider"]
        F --> OAI["OpenAIImageProvider"]

        R2 --> RS["RecommendationService<br/>(Facade)"]
        RS --> ST["Content · Hybrid · Popular<br/>(Strategy)"]
        ST --> MMR["Diversidad MMR"]

        R3 --> PS["PricingService<br/>(Facade)"]
        PS --> EST["ComparablePriceEstimator<br/>IQR + confianza"]
        PS --> ADV["LlmPriceAdvisor"] --> TM["TextModel<br/>(Adapter)"]
    end

    MOD -.-> OPENAI[("OpenAI")]
    OAI -.-> OPENAI
    TM -.-> OPENAI
```

## Funciones

| Ruta | Qué hace |
|---|---|
| `GET /health` | Estado, versión, proveedores activos y commit desplegado (sin clave). |
| `POST /v1/designs` | Imágenes de propuesta para un encargo (simuladas u OpenAI). |
| `POST /v1/recommendations` | Ordena obras según los gustos del cliente, con explicación en español. |
| `POST /v1/pricing/suggest` | Sugiere un precio a partir de piezas comparables, con nivel de confianza. |
| `POST /v1/similar` | Obras parecidas a una obra, con los rasgos que comparten. |
| `POST /v1/bids/assess` | Marca pujas sospechosas para el administrador (nunca las rechaza). |
| `GET /v1/metrics` | Contadores por ruta, latencia, imágenes del día y costo estimado. |

Las recomendaciones y el precio usan **códigos de texto** (`"rojo"`, `"colibri"`, `"bandeja"`)
y no ids, para funcionar con los tags actuales del backend y con los catálogos de la v2.
Los códigos se normalizan: `"Colibrí"` y `"colibri"` son lo mismo.

La guía para el backend está en [`docs/integracion-backend.md`](docs/integracion-backend.md) y
los cambios de cada versión en [`CHANGELOG.md`](CHANGELOG.md).

## Requisitos

- Python 3.12 o superior.
- Una clave de OpenAI solo si se activa un proveedor `openai`.

## Cómo correrlo en local

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env    # y llena AI_SERVICE_KEY (y OPENAI_API_KEY si la usas)
uvicorn app.main:app --reload
```

- Documentación interactiva con ejemplos: <http://localhost:8000/docs>
- Prueba rápida: `curl http://localhost:8000/health`

Con `IMAGE_PROVIDER=fake` y `TEXT_PROVIDER=none` (valores por defecto) el servicio **no gasta
nada**: las imágenes las dibuja Pillow y el precio sale solo de los comparables.

## Protección del saldo

| Protección | Cómo | Respuesta |
|---|---|---|
| Límite diario de imágenes | `DAILY_IMAGE_LIMIT` imágenes pagas por día (hora de Colombia). Si una generación falla, la imagen no cuenta. | `429 budget_exceeded` + `Retry-After` |
| Solicitudes por minuto | `RATE_LIMIT_PER_MINUTE` por clave e IP, ventana deslizante de 60 s. Cuenta también los intentos con clave equivocada. | `429 rate_limited` + `Retry-After` |
| Moderación | Con OpenAI, el texto del cliente pasa por el endpoint de moderación **antes** de pagar la imagen. | `400 content_rejected` |
| Tamaño del cuerpo | `MAX_REQUEST_BYTES` (1 MB). | `413 invalid_request` |

> Los contadores viven en memoria: se reinician cuando Render reinicia o despierta el servicio.
> Configura también un **límite de gasto en el proyecto de OpenAI**.

## Observabilidad

- **Logs en JSON** (una línea por evento) con `request_id`, ruta, estado, duración, proveedor,
  modelo y código de error. **Nunca** se registran claves, headers, cuerpos, prompts ni datos
  del cliente; las excepciones se registran sin su mensaje.
- **`X-Request-ID`**: si el backend lo envía (hasta 64 caracteres `A-Z a-z 0-9 . _ -`) se
  reutiliza; si no, se genera. Siempre se devuelve en la respuesta y aparece en cada log.
- **`GET /v1/metrics`**: contadores, errores por código y latencia promedio por ruta; imágenes
  del día por proveedor, tokens de texto y **costo estimado** con los precios configurados.

## Variables de entorno

| Variable | Uso | Por defecto |
|---|---|---|
| `AI_SERVICE_KEY` | Clave que debe enviar el backend | (obligatoria) |
| `IMAGE_PROVIDER` | `fake` u `openai` | `fake` |
| `OPENAI_API_KEY` | Clave de OpenAI | vacía |
| `OPENAI_IMAGE_MODEL` | Modelo de imágenes | `gpt-image-2` |
| `OPENAI_IMAGE_QUALITY` | `low`, `medium` o `high` | `medium` |
| `OPENAI_IMAGE_SIZE` | Tamaño de la imagen | `1024x1024` |
| `OPENAI_IMAGE_FORMAT` | `webp`, `jpeg` o `png` | `webp` |
| `OPENAI_IMAGE_COMPRESSION` | Calidad 0–100 para webp/jpeg | `80` |
| `MODERATION_ENABLED` | Moderar el texto antes de generar (solo con OpenAI) | `true` |
| `OPENAI_MODERATION_MODEL` | Modelo de moderación | `omni-moderation-latest` |
| `TEXT_PROVIDER` | `none` u `openai` (precio sugerido) | `none` |
| `OPENAI_TEXT_MODEL` | Modelo de texto | `gpt-6-luna` en `.env.example` |
| `PROVIDER_TIMEOUT_SECONDS` | Espera máxima a OpenAI para imágenes | `90` |
| `MAX_IMAGES_PER_REQUEST` | Imágenes por llamada | `2` |
| `DAILY_IMAGE_LIMIT` | Imágenes pagas por día | `30` |
| `RATE_LIMIT_PER_MINUTE` | Solicitudes por minuto por clave e IP | `20` |
| `MAX_REQUEST_BYTES` | Tamaño máximo del cuerpo | `1000000` |
| `RECO_WEIGHT_COLOR` / `_SHAPE` / `_STYLE` / `_MOTIF` | Pesos de la similitud | `1.0` / `1.5` / `1.2` / `1.3` |
| `RECO_BUDGET_SHARE` | Peso del presupuesto en el puntaje (0–1) | `0.15` |
| `RECO_PROFILE_SHARE` | Peso del perfil frente a las interacciones (0–1) | `0.6` |
| `RECO_DIVERSITY` | Diversidad por taller con MMR (0 = sin diversidad) | `0.3` |
| `RECO_SEMANTIC_WEIGHT` | Peso del parecido con las obras que le gustaron (con índice) | `0.35` |
| `RECO_MASTER_WEIGHT` | Peso de la afinidad con el estilo de cada maestro (con índice) | `0.15` |
| `CATALOG_INDEX_PATH` | Ruta del índice de obras | `data/catalog_index.json` |
| `BID_MODEL_PATH` | Ruta del detector de pujas entrenado | `models/bid_anomaly.joblib` |
| `OPENAI_IMAGE_COST_USD` | Precio por imagen para el costo estimado | `0.053` |
| `OPENAI_TEXT_INPUT_USD_PER_MTOK` / `_OUTPUT_` | Precio por millón de tokens de texto | `0.10` / `0.50` |
| `DOCS_ENABLED` | Mostrar `/docs`, `/redoc` y `/openapi.json` | `true` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING` o `ERROR` | `INFO` |

El archivo `.env` nunca se sube al repositorio; está en `.gitignore`.

## Pruebas y linter

```bash
pytest
ruff check .
pip-audit -r requirements.txt   # vulnerabilidades conocidas en las dependencias
```

GitHub Actions (`.github/workflows/ci.yml`) corre lo mismo en cada push y pull request; en
`main` revisa cada commit, porque Render despliega cada push.

Las pruebas **nunca llaman a OpenAI**: usan el proveedor simulado o mocks, y arman la
configuración en memoria (no leen tu `.env`).

## Patrones de diseño

| Patrón | Dónde | Para qué |
|---|---|---|
| Singleton | `Settings` con `lru_cache` (`app/core/config.py`) | Leer la configuración una sola vez. |
| Adapter | `ImageProvider`, `TextModel` y `ContentModerator` (OpenAI y alternativas) | Que los servicios no dependan del SDK de OpenAI. |
| Null Object | `DisabledTextModel`, `NoopContentModerator` | Funcionar sin OpenAI sin preguntar por `None`. |
| Factory Method | `ImageProviderFactory` | Elegir el proveedor según `IMAGE_PROVIDER`. |
| Builder | `DesignPromptBuilder` (y `for_request` como director) | Armar el prompt paso a paso, con composición por imagen. |
| Strategy | `ContentBasedStrategy`, `HybridStrategy`, `PopularityStrategy` | Cambiar el algoritmo de recomendación según los datos. |
| Template Method | `RecommendationStrategy.rank` | Cada estrategia solo define su vector de gustos; el resto se comparte. |
| Facade | `DesignService`, `RecommendationService`, `PricingService` | Que las rutas no conozcan proveedores ni estrategias. |
| Chain of Responsibility | Middlewares ASGI y dependencias de `/v1` | Request ID → logs → tamaño → límite → clave → ruta. |

## Recomendaciones

**¿Por qué no se entrenan?** MUSEO tiene todavía **muy pocos datos reales** (pocas obras,
clientes e interacciones). Un modelo entrenado con tan pocos datos se sobreajusta. Por eso se usa
**similitud por contenido**: obras y perfiles son vectores de colores, forma, estilo y figuras,
comparados con similitud coseno ponderada (pesos configurables), más un ajuste por presupuesto.

- **Híbrida:** suma el gusto que se deduce de las interacciones (ver según la duración, acercar,
  favorito, carrito, compra, compartir, contactar).
- **Diversidad (MMR):** evita que un solo taller llene la lista; una pieza casi igual de buena de
  otro taller sube antes que una tercera copia del mismo taller.
- **Explicación:** cada resultado trae `reasons` y una frase corta en español.
- **Calidad medida:** `tests/test_recommendation_quality.py` usa un catálogo sintético de 80
  piezas y mide NDCG@10, el efecto de las interacciones y del presupuesto, la diversidad, la
  monotonía y el determinismo.

## Cómo aprende la IA de las obras

No se entrena una red neuronal: hay muy pocas obras para eso. En cambio, la IA **mira y describe**
cada obra una vez y guarda lo que aprendió en `data/catalog_index.json`.

1. **Mira cada obra.** `scripts/build_catalog_index.py` (se corre en un PC, no en Render) le
   muestra la foto principal de cada pieza a un modelo de visión (`gpt-6-luna`) y le pide una
   ficha en español: técnica, colores, figuras, estilo, forma, sensación y 3 a 5 rasgos que la
   distinguen ("flora densa", "retrato frontal", "espirales negras de gran formato").
2. **La convierte en números.** Esa ficha, junto con los datos del catálogo, se transforma en un
   *embedding* (`text-embedding-3-small`): una lista de 256 números en la que dos obras
   parecidas quedan cerca. Así "parecido" se puede medir.
3. **Arma el perfil de cada maestro.** Promedia los números de sus obras y guarda sus rasgos más
   repetidos. Por ejemplo, Gilberto Granja queda asociado a "flora densa" y "grecas geométricas".
4. **Lo usa al recomendar.** Con la estrategia híbrida, si alguien vio, guardó o compró una obra,
   las obras más parecidas suben (más si la compró que si solo la miró), y también las de los
   maestros cuyo estilo coincide con lo que le gustó. La explicación lo dice: "Porque te gustó
   «Jarrón Flora Azul» de Gilberto Granja" o "Del estilo de María Cabrera: retrato frontal".
5. **"Obras parecidas".** `POST /v1/similar` usa los mismos números para la ficha de una pieza.

Detalles:

- Generar el índice de las 21 obras costó **0.0037 USD** una sola vez. Al responder no se llama a
  OpenAI: todo sale del índice, que el servicio carga al arrancar.
- Si el índice no existe o no es válido, el servicio funciona como antes.
- Para que una obra use lo aprendido, el backend envía su `slug` (por ejemplo
  `bargueno-colonial`). Sin `slug`, se recomienda como siempre.
- Cuando se agreguen obras nuevas, se vuelve a correr el script y se sube el nuevo índice:

  ```bash
  python scripts/build_catalog_index.py            # usa OPENAI_API_KEY del .env
  python scripts/build_catalog_index.py --dry-run  # sin OpenAI, para probar
  ```

## Cómo se entrenó el detector de pujas

> **Los datos son SINTÉTICOS.** MUSEO todavía no tiene historial de subastas. Las métricas de
> abajo dicen qué tan bien el detector reconoce los patrones que simulamos, no qué tan bien
> funcionará con compradores reales. Cuando haya subastas reales, hay que volver a entrenar y
> medir con ellas.

1. **Simulamos subastas.** `scripts/generate_auction_data.py` crea 168 subastas de 3 días para
   las obras del museo (2.317 pujas, semilla fija 2026, `data/auctions_synthetic.csv`).
   - **Normales:** varios postores, cada uno con un precio máximo que está dispuesto a pagar,
     incrementos razonables y pujas en los últimos minutos (sniping legítimo).
   - **Sospechosas (13,5 %), etiquetadas:** puja inflada (*shill*: una cuenta sube el precio con
     el paso mínimo justo después de los demás y se retira antes del cierre), ráfagas tipo bot,
     saltos exagerados y cuentas nuevas con montos muy altos.
2. **Convertimos cada puja en números** (`app/auctions/bid_features.py`): cuántas veces supera
   la puja actual y el precio base, en cuántos incrementos mínimos sube, el tiempo desde su puja
   anterior y desde la última puja de la subasta, cuántas pujas hizo en el último minuto, la
   antigüedad de la cuenta, cuántas veces subió su propia puja y cuánto falta para el cierre. El
   servicio usa exactamente la misma función.
3. **Entrenamos un Isolation Forest** (`scripts/train_bid_model.py`, scikit-learn). No usa las
   etiquetas: aprende cómo se ve una puja común y mide qué tan rara es una nueva. Separamos por
   subasta: 70 % para entrenar y 30 % para evaluar, sin mezclar pujas de una misma subasta.
4. **Lo evaluamos** con las subastas que no vio (654 pujas, 74 sospechosas):

   | Métrica | Valor |
   |---|---|
   | Precisión (de las que marcó, cuántas eran sospechosas) | 0,56 |
   | Recall (de las sospechosas, cuántas marcó) | 0,77 |
   | F1 | 0,65 |
   | Falsas alarmas (pujas normales marcadas) | 7,6 % |

   | Matriz de confusión | Marcada | No marcada |
   |---|---|---|
   | **Sospechosa** | 57 | 17 |
   | **Normal** | 44 | 536 |

   Recall por tipo: saltos exagerados 100 %, cuentas nuevas con montos altos 100 %, ráfagas tipo
   bot 85 %, puja inflada 55 %. La puja inflada es la más difícil: una sola puja con el paso
   mínimo se parece a una normal; se nota cuando la cuenta acumula pujas.
5. **Lo que no funcionó:** elegir el umbral con una parte de validación mejoraba la validación
   pero empeoraba la prueba (F1 0,58): con tan pocos datos se sobreajusta. Por eso se deja el
   umbral natural del modelo.

**Cómo se usa:** `POST /v1/bids/assess` marca la puja como `SUSPICIOUS` si el modelo la ve rara
**o** si hay una señal clara (salto de 10 veces la puja actual, 5 pujas en un minuto, cuenta
nueva con un monto de 3 veces el precio base). Las razones salen de reglas fijas y están en
español. **Nunca rechaza una puja**: solo la deja marcada para el administrador. Sin el modelo,
funciona con las reglas.

Para volver a generar los datos y el modelo (en un PC, no en Render):

```bash
python scripts/generate_auction_data.py   # data/auctions_synthetic.csv
python scripts/train_bid_model.py         # models/bid_anomaly.joblib y bid_anomaly_metrics.json
```

El modelo pesa 436 KB y con él cargado el servicio usa unos 190 MB de memoria: cabe en el plan
gratis de Render (512 MB).

## Precio sugerido

El precio es una **sugerencia** para el artesano; él decide.

1. Se descartan los **precios atípicos** con la regla del rango intercuartílico (IQR).
2. Se calcula la mediana ponderada por parecido (forma, figuras, tamaño; las vendidas pesan más)
   y el rango entre los percentiles 25 y 75.
3. `confidence` es `high`, `medium` o `low` según cuántos comparables hay y qué tan parecidos son.
4. Si hay modelo de texto, ajusta **dentro del rango** y redacta la explicación.

Con menos de 3 comparables, haya o no modelo de texto, responde `422 not_enough_data`:
**nunca inventa un precio**.

**Modo subasta** (`"mode": "auction"`): además devuelve el precio de salida (percentil 25),
la reserva (mediana ponderada de los comparables, sin el ajuste del modelo de texto) y el
incremento mínimo (una décima parte del rango intercuartílico, al menos 1). Todo sale de los
comparables.

## Despliegue en Render (Docker)

1. En Render, crea un **Web Service** desde este repositorio con entorno **Docker**, rama `main`
   y *Auto-Deploy* activado.
2. En *Environment* agrega las variables de la tabla (como mínimo `AI_SERVICE_KEY`). En
   producción conviene `DOCS_ENABLED=false`.
3. *Health check path*: `/health`. El campo `commit` muestra qué commit está desplegado
   (Render lo pone solo en la variable `RENDER_GIT_COMMIT`).
4. Render inyecta la variable `PORT`; el `Dockerfile` ya la usa.
5. En el backend configura `AI_SERVICE_URL` (la URL de Render) y la misma `AI_SERVICE_KEY`.

### Probar el despliegue (smoke test)

```bash
# Linux/macOS
AI_SERVICE_KEY=<clave> python scripts/smoke_test.py
# Windows PowerShell
$env:AI_SERVICE_KEY="<clave>"; python scripts/smoke_test.py
```

Revisa `/health`, que `/v1` rechace las llamadas sin clave, las recomendaciones y el precio
sugerido contra Render (o contra `AI_SERVICE_URL`). **No genera imágenes**, así que no gasta.
La clave se lee del entorno y nunca se imprime; el código de salida es 0 si todo pasa.

> **Ojo con el plan gratis:** Render "duerme" el servicio tras unos 15 minutos sin uso y la
> primera llamada después puede tardar cerca de un minuto en responder mientras arranca. El
> backend debe tener timeouts generosos (120 s para diseños) y seguir funcionando con sus reglas
> fijas si la IA no responde. Al despertar se reinician los contadores en memoria.
