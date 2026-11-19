# Changelog

Cambios importantes del servicio de IA de MUSEO. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones con
[Versionado Semántico](https://semver.org/lang/es/).

## [1.1.0] - 2026-11-19

Todos los cambios son compatibles con la versión 1.0.0: solo se agregan campos y códigos.

### Agregado

- **Integración continua:** GitHub Actions corre `ruff`, `pytest` y `pip-audit` en cada push y
  pull request; en `main` valida cada commit. Insignia en el README.
- **Protección del saldo:**
  - Límite diario de imágenes pagas (`DAILY_IMAGE_LIMIT`, 30): `429 budget_exceeded`.
  - Límite de solicitudes por minuto por clave e IP (`RATE_LIMIT_PER_MINUTE`, 20):
    `429 rate_limited`. Ambos traen el header `Retry-After`.
  - Moderación del texto del cliente con OpenAI **antes** de generar la imagen:
    `400 content_rejected` sin gastar en la imagen.
  - Tamaño máximo del cuerpo (`MAX_REQUEST_BYTES`, 1 MB): `413 invalid_request`.
- **Imágenes más livianas:** formato `webp` (por defecto), `jpeg` o `png` con compresión
  (`OPENAI_IMAGE_FORMAT`, `OPENAI_IMAGE_COMPRESSION`); `mime_type` dice el formato real.
- **Variaciones de diseño:** con `count > 1` cada imagen tiene una composición distinta (`top`,
  `three_quarter`, `detail`). Cada imagen trae `composition` y su `prompt`. Se generan en
  paralelo.
- **Observabilidad:**
  - Logs en JSON con `request_id`, ruta, estado, duración, proveedor, modelo y código de error,
    sin claves, prompts ni datos personales.
  - Header `X-Request-ID`: se recibe o se genera, y se devuelve.
  - `GET /v1/metrics`: contadores por ruta, latencia, imágenes del día y costo estimado.
  - `/health` muestra el `commit` desplegado en Render.
- **Recomendaciones:**
  - Diversidad por taller con MMR (`RECO_DIVERSITY`).
  - Campo `explanation` con una frase corta en español en cada resultado.
  - Pesos configurables (`RECO_WEIGHT_*`, `RECO_BUDGET_SHARE`, `RECO_PROFILE_SHARE`).
  - Pruebas de calidad con perfiles sintéticos (NDCG, interacciones, presupuesto, diversidad).
- **Precio sugerido:**
  - Se descartan los precios atípicos de los comparables (IQR).
  - Campo `confidence` (`low`, `medium`, `high`).
- **Prueba del despliegue:** `scripts/smoke_test.py` revisa `/health`, la autenticación, las
  recomendaciones y el precio en Render, sin generar imágenes.
- **Documentación:** ejemplos y descripciones en `/docs`, diagrama de arquitectura (Mermaid) y
  tabla de patrones en el README, y `DOCS_ENABLED` para ocultar la documentación en producción.

### Cambiado

- Con `count > 1` se hace una llamada a OpenAI por imagen (una por composición) en vez de una
  sola con `n=count`; el tiempo total no aumenta porque van en paralelo.
- El proveedor simulado también respeta el formato de imagen configurado.
- La documentación OpenAPI ya no anuncia el `422 Validation Error` automático de FastAPI: los
  errores de validación son `400 invalid_request`, como siempre.

### Corregido

- Las respuestas JSON declaran `charset=utf-8`.

## [1.0.0] - 2026-11-19

### Agregado

- `GET /health`, autenticación con `X-API-Key` y formato común de errores.
- `POST /v1/designs` con proveedor simulado (Pillow) y OpenAI, prompt con Builder y fábrica de
  proveedores.
- `POST /v1/recommendations` con estrategias por contenido, híbrida y por popularidad, usando
  códigos de texto.
- `POST /v1/pricing/suggest` con comparables y asesor opcional con modelo de texto.
- Guía de integración para el backend, Dockerfile y despliegue en Render.
