# MUSEO — Servicio de IA

Servicio de inteligencia artificial de **MUSEO**, la galería 3D y tienda del Barniz de Pasto
Mopa-Mopa. Proyecto final del curso *Patrones de Software* (Universidad Cooperativa de Colombia).

```
Frontend 3D ──► Backend Spring ──► Este servicio (FastAPI) ──► OpenAI
```

- Solo lo llama el backend; el frontend nunca habla con este servicio.
- No tiene estado ni base de datos: recibe en el JSON lo que necesita y responde.
- Todas las rutas, menos `/health`, piden el header `X-API-Key: <AI_SERVICE_KEY>`.
- Los errores tienen siempre la forma `{"code": "...", "message": "..."}`.

## Funciones

| Ruta | Qué hace |
|---|---|
| `GET /health` | Estado del servicio y proveedores activos (sin clave). |
| `POST /v1/designs` | Genera imágenes de propuesta para un encargo (simuladas u OpenAI). |
| `POST /v1/recommendations` | Ordena obras según los gustos del cliente. |
| `POST /v1/pricing/suggest` | Sugiere un precio a partir de piezas comparables. |

Las recomendaciones y el precio usan **códigos de texto** (`"rojo"`, `"colibri"`, `"bandeja"`)
y no ids, para funcionar con los tags actuales del backend y con los catálogos de la v2.
Los códigos se normalizan: `"Colibrí"` y `"colibri"` son lo mismo.

La guía completa para el backend está en `docs/integracion-backend.md`.

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

- Documentación interactiva: <http://localhost:8000/docs>
- Prueba rápida: `curl http://localhost:8000/health`

Con `IMAGE_PROVIDER=fake` y `TEXT_PROVIDER=none` (valores por defecto) el servicio **no gasta
nada**: las imágenes las dibuja Pillow y el precio sale solo de los comparables.

## Variables de entorno

| Variable | Uso | Por defecto |
|---|---|---|
| `AI_SERVICE_KEY` | Clave que debe enviar el backend | (obligatoria) |
| `IMAGE_PROVIDER` | `fake` u `openai` | `fake` |
| `OPENAI_API_KEY` | Clave de OpenAI | vacía |
| `OPENAI_IMAGE_MODEL` | Modelo de imágenes | `gpt-image-2` |
| `OPENAI_IMAGE_QUALITY` | `low`, `medium` o `high` | `medium` |
| `OPENAI_IMAGE_SIZE` | Tamaño de la imagen | `1024x1024` |
| `TEXT_PROVIDER` | `none` u `openai` (precio sugerido) | `none` |
| `OPENAI_TEXT_MODEL` | Modelo de texto | `gpt-6-luna` en `.env.example` |
| `PROVIDER_TIMEOUT_SECONDS` | Espera máxima a OpenAI | `90` |
| `MAX_IMAGES_PER_REQUEST` | Imágenes por llamada | `2` |

El archivo `.env` nunca se sube al repositorio; está en `.gitignore`.

## Pruebas y linter

```bash
pytest
ruff check .
```

Las pruebas **nunca llaman a OpenAI**: usan el proveedor simulado o mocks, y arman la
configuración en memoria (no leen tu `.env`).

## Patrones de diseño

| Patrón | Dónde |
|---|---|
| Singleton | `Settings`, cargado una sola vez con `lru_cache` (`app/core/config.py`) |
| Adapter | `ImageProvider` (OpenAI y simulado) y `TextModel` (OpenAI y deshabilitado) |
| Factory Method | `ImageProviderFactory` elige el proveedor según la configuración |
| Builder | `DesignPromptBuilder` arma el prompt paso a paso |
| Strategy | Estrategias de recomendación: por contenido e híbrida |
| Facade | Un servicio por área (`DesignService`, `RecommendationService`, `PricingService`) |

## ¿Por qué las recomendaciones no se entrenan?

MUSEO tiene todavía **muy pocos datos reales** (pocas obras, pocos clientes y pocas
interacciones). Un modelo entrenado con tan pocos datos se sobreajusta y da resultados
inestables. Por eso se usa **similitud por contenido**: cada obra y cada perfil se convierten en
vectores de colores, forma, estilo y figuras, y se comparan con similitud coseno ponderada más
un ajuste por presupuesto. La estrategia híbrida suma el gusto que se deduce de las
interacciones (ver, acercar, favorito, carrito, compra, compartir, contactar). Es determinista,
explicable (cada resultado trae sus razones) y fácil de probar. Cuando haya suficientes datos se
podrá agregar otra estrategia sin tocar las rutas.

## Precio sugerido

El precio es una **sugerencia** para el artesano; él decide. Se calcula con la mediana
ponderada por parecido de piezas comparables y un rango intercuartílico. Si hay modelo de texto,
este puede ajustar dentro del rango y redactar la explicación. Con menos de 3 comparables, haya o
no modelo de texto, el servicio responde `422 not_enough_data`: **nunca inventa un precio**.

## Despliegue en Render (Docker)

1. En Render, crea un **Web Service** desde este repositorio con entorno **Docker**.
2. En *Environment* agrega las variables de la tabla (como mínimo `AI_SERVICE_KEY`).
3. *Health check path*: `/health`.
4. Render inyecta la variable `PORT`; el `Dockerfile` ya la usa.
5. En el backend configura `AI_SERVICE_URL` (la URL de Render) y la misma `AI_SERVICE_KEY`.

> **Ojo con el plan gratis:** Render "duerme" el servicio tras unos 15 minutos sin uso y la
> primera llamada después puede tardar cerca de un minuto en responder mientras arranca. El
> backend debe tener timeouts generosos (120 s para diseños) y seguir funcionando con sus reglas
> fijas si la IA no responde.
