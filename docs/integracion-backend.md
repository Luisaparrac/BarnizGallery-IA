# Integración del backend con el servicio de IA

Guía para la encargada de **BarnizGallery-Backend** (Spring). Explica el contrato del servicio de
IA, cómo crear `AiServiceClient` para reemplazar `DisabledAiClient` y qué hacer cuando la IA
falla.

```
Frontend 3D ──► Backend Spring ──► Servicio de IA (FastAPI) ──► OpenAI
```

- **El frontend nunca llama al servicio de IA.** Solo lo llama el backend.
- **El servicio de IA no tiene estado ni base de datos:** el backend le envía en el JSON todo lo
  que necesita y es el backend quien guarda los resultados en PostgreSQL.
- **La IA es opcional:** si no responde, el backend sigue funcionando con sus reglas fijas.

## 1. Variables de entorno del backend

| Variable | Ejemplo | Uso |
|---|---|---|
| `AI_SERVICE_URL` | `https://museo-ia.onrender.com` | URL base del servicio, sin `/` final |
| `AI_SERVICE_KEY` | (secreta) | La misma `AI_SERVICE_KEY` configurada en el servicio de IA |

Nunca las subas al repositorio; van en el `.env` local y en el panel de Render.

```properties
# application.properties
ai.service.url=${AI_SERVICE_URL:}
ai.service.key=${AI_SERVICE_KEY:}
```

Si `AI_SERVICE_URL` está vacía, sigue usando `DisabledAiClient`.

## 2. Reglas generales del contrato (versión 1)

- **Autenticación:** todas las rutas, menos `/health`, exigen el header
  `X-API-Key: <AI_SERVICE_KEY>`. Si falta o es incorrecta, la respuesta es `401`.
- **JSON en `snake_case`.** Con Jackson usa `@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)`
  en los DTO.
- **Códigos de texto, no ids:** recomendaciones y precio usan códigos como `"rojo"`, `"colibri"`,
  `"bandeja"`. Sirven los tags de texto actuales y luego los códigos de los catálogos de la v2.
  El servicio los normaliza (minúsculas, sin tildes, sin espacios extra): `"Colibrí"` = `"colibri"`.
- **Errores** con la forma `{"code": "...", "message": "..."}`. El `message` está en español y se
  puede mostrar; decide siempre por el `code`:

| HTTP | `code` | Significado | Qué hace el backend |
|---|---|---|---|
| 400 | `invalid_request` | El JSON no cumple el contrato | Es un error del backend: registrarlo y corregir |
| 400 | `content_rejected` | OpenAI rechazó el contenido del encargo | Mostrar al cliente que cambie la descripción |
| 401 | `unauthorized` | Falta `X-API-Key` o no es válida | Revisar `AI_SERVICE_KEY` |
| 422 | `not_enough_data` | Pocos datos (precio con menos de 3 comparables) | No sugerir precio |
| 502 | `provider_error` | OpenAI falló | Usar las reglas fijas; se puede reintentar más tarde |
| 503 | `feature_disabled` | La función no está activada en el servicio | Usar las reglas fijas |
| 504 | `provider_timeout` | OpenAI tardó demasiado | Usar las reglas fijas; se puede reintentar más tarde |

### `GET /health`

Sin clave. Útil para despertar el servicio en Render (ver sección 7).

```json
{"status": "ok", "version": "1.0.0", "image_provider": "fake", "text_provider": "none"}
```

### `POST /v1/designs`: diseños para encargos

Entrada:

```json
{
  "request_id": 42,
  "title": "Bandeja para mi abuela",
  "description": "Bandeja redonda con colibríes y flores...",
  "shape": "Bandeja",
  "style": "Tradicional",
  "colors": [{"name": "Rojo", "hex": "#B3261E"}],
  "motifs": ["Colibrí", "Flores"],
  "size_notes": "unos 30 cm",
  "language": "es",
  "count": 1
}
```

| Campo | Reglas |
|---|---|
| `request_id` | Obligatorio, entero ≥ 1 (id del encargo en el backend; solo para registro) |
| `title` | Obligatorio, 1–120 caracteres |
| `description` | Opcional, hasta 1000 caracteres |
| `shape`, `style` | Obligatorios, 1–60 caracteres (texto libre en español) |
| `colors` | Hasta 8; `hex` con formato `#RRGGBB` |
| `motifs` | Hasta 10 |
| `size_notes` | Opcional, hasta 200 caracteres |
| `language` | `es` (por defecto) o `en` |
| `count` | 1 por defecto; como máximo `MAX_IMAGES_PER_REQUEST` del servicio (2), si no da `400` |

Salida:

```json
{
  "provider": "openai",
  "model": "gpt-image-2",
  "prompt": "<prompt final enviado>",
  "images": [{"image_base64": "iVBORw0KGgo...", "mime_type": "image/png"}]
}
```

Con `IMAGE_PROVIDER=fake` el servicio devuelve un PNG dibujado (sin costo), con
`"provider": "fake"`, ideal para desarrollar el flujo completo.

### `POST /v1/recommendations`: recomendaciones por gustos

Entrada:

```json
{
  "profile": {
    "colors": ["rojo", "verde"], "shapes": ["bandeja"], "styles": ["tradicional"],
    "motifs": ["colibri"],
    "budget": {"min": 20, "max": 120, "currency": "USD"}
  },
  "interactions": [{"artwork_id": 5, "action": "VIEW", "duration_seconds": 40}],
  "candidates": [
    {"artwork_id": 5, "store_id": 2, "colors": ["rojo", "amarillo"], "shape": "bandeja",
     "style": "tradicional", "motifs": ["colibri"], "price": 80, "currency": "USD",
     "popularity": 12}
  ],
  "limit": 10
}
```

- Todo es opcional menos el `artwork_id` de cada candidato. `limit` va de 1 a 100 (10 por defecto).
- `action`: `VIEW`, `ZOOM`, `FAVORITE`, `CART`, `PURCHASE`, `SHARE` o `CONTACT`.
  `duration_seconds` solo cuenta para `VIEW`.
- **Las interacciones solo se usan si su `artwork_id` está entre los `candidates`**, porque el
  servicio solo conoce las características de las obras que recibe. Envía como candidatas también
  las obras con las que el cliente interactuó (o al menos las más recientes).
- `currency` son 3 letras (`USD`, `COP`). El presupuesto solo se compara con obras de la misma
  moneda; el servicio no convierte monedas.
- Envía solo obras disponibles: el servicio no sabe cuáles están vendidas.

Salida:

```json
{
  "strategy": "hybrid",
  "items": [
    {"artwork_id": 5, "store_id": 2, "score": 0.9476,
     "reasons": {"colors": ["rojo", "amarillo"], "shape": true, "style": true,
                 "motifs": ["colibri"], "budget": true}}
  ]
}
```

En `reasons` aparecen tanto lo que el cliente declaró en su perfil como lo que se dedujo de sus
interacciones (aquí `amarillo`, porque vio esa obra 40 segundos).

- `strategy`: `content` (solo perfil), `hybrid` (perfil y/o interacciones) o `popular` (sin
  perfil ni interacciones útiles: ordena por `popularity`).
- `score` va de 0 a 1. `reasons` sirve para mostrar "Te puede gustar por…".
  `reasons.budget` es `null` cuando no se puede comparar (sin presupuesto, sin precio u otra moneda).
- Es determinista: la misma entrada da siempre el mismo orden.

### `POST /v1/pricing/suggest`: precio sugerido

Entrada:

```json
{
  "piece": {
    "shape": "bandeja", "style": "tradicional", "colors": ["rojo"], "motifs": ["colibri"],
    "width_cm": 30, "height_cm": 30, "depth_cm": 3,
    "technique": "barniz", "work_hours": 20
  },
  "comparables": [
    {"artwork_id": 9, "shape": "bandeja", "style": "tradicional", "colors": ["rojo"],
     "motifs": ["colibri", "flores"], "width_cm": 28, "height_cm": 28,
     "price": 90, "currency": "USD", "sold": true}
  ],
  "currency": "USD"
}
```

- `piece.shape` es obligatorio; las medidas, la técnica y las horas son opcionales pero mejoran
  el resultado.
- En cada comparable son obligatorios `shape`, `price` (> 0) y `currency`.
- Solo se usan los comparables en la `currency` pedida.

Salida:

```json
{"suggested_price": 95, "min_price": 90, "max_price": 115, "currency": "USD",
 "method": "comparables",
 "explanation": "Basado en 6 piezas parecidas, 3 ya vendidas, con un parecido promedio del 100%..."}
```

- `method`: `comparables`, o `comparables+llm` si el servicio tiene modelo de texto activado. El
  modelo de texto solo puede mover el precio **dentro** del rango.
- Sin modelo de texto y con menos de 3 comparables: `422 not_enough_data`. Sin ningún
  comparable siempre es `422`: **el servicio nunca inventa un precio.**
- Es una **sugerencia** para el artesano: muéstrala como tal y deja que él decida.

## 3. `AiServiceClient` en Spring (Adapter)

`AiServiceClient` es un **Adapter**: implementa la misma interfaz que hoy implementa
`DisabledAiClient` (aquí la llamamos `AiClient`; **ajusta los nombres de métodos y DTO a los que
ya existen en el backend**) y traduce cada llamada a HTTP.

Se usan dos `RestClient`: uno con **120 s** de lectura para diseños (generar imágenes tarda) y otro
con **10 s** para recomendaciones y precio.

```java
@Configuration
public class AiClientConfig {

    @Bean
    public AiClient aiClient(
            @Value("${ai.service.url:}") String url,
            @Value("${ai.service.key:}") String key) {
        if (url.isBlank() || key.isBlank()) {
            return new DisabledAiClient();
        }
        return new AiServiceClient(
                restClient(url, key, Duration.ofSeconds(120)),
                restClient(url, key, Duration.ofSeconds(10)));
    }

    private static RestClient restClient(String url, String key, Duration readTimeout) {
        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(10));
        factory.setReadTimeout(readTimeout);
        return RestClient.builder()
                .baseUrl(url)
                .defaultHeader("X-API-Key", key)
                .requestFactory(factory)
                .build();
    }
}
```

```java
public class AiServiceClient implements AiClient {

    private static final Logger log = LoggerFactory.getLogger(AiServiceClient.class);

    private final RestClient designs;   // 120 s
    private final RestClient quick;     // 10 s

    public AiServiceClient(RestClient designs, RestClient quick) {
        this.designs = designs;
        this.quick = quick;
    }

    @Override
    public DesignResult generateDesign(DesignAiRequest request) {
        return designs.post().uri("/v1/designs")
                .contentType(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .onStatus(HttpStatusCode::isError, AiServiceClient::throwAiError)
                .body(DesignResult.class);
    }

    @Override
    public RecommendationResult recommend(RecommendationAiRequest request) {
        return quick.post().uri("/v1/recommendations")
                .contentType(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .onStatus(HttpStatusCode::isError, AiServiceClient::throwAiError)
                .body(RecommendationResult.class);
    }

    @Override
    public PriceSuggestion suggestPrice(PricingAiRequest request) {
        return quick.post().uri("/v1/pricing/suggest")
                .contentType(MediaType.APPLICATION_JSON)
                .body(request)
                .retrieve()
                .onStatus(HttpStatusCode::isError, AiServiceClient::throwAiError)
                .body(PriceSuggestion.class);
    }

    private static void throwAiError(HttpRequest req, ClientHttpResponse res) throws IOException {
        var error = new ObjectMapper().readValue(res.getBody(), AiError.class);
        log.warn("Servicio de IA respondió {} {}", res.getStatusCode().value(), error.code());
        throw new AiServiceException(res.getStatusCode().value(), error.code(), error.message());
    }
}
```

```java
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record AiError(String code, String message) {}

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record DesignResult(String provider, String model, String prompt, List<DesignImage> images) {}

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record DesignImage(String imageBase64, String mimeType) {}
```

`AiServiceException` es una excepción propia (`RuntimeException`) con `status`, `code` y
`message`. Los timeouts y errores de red llegan como `ResourceAccessException`.

## 4. Qué hacer si la IA falla

La regla: **un fallo de la IA nunca rompe el flujo del usuario.**

| Función | Si falla (`5xx`, timeout, `ResourceAccessException`) |
|---|---|
| Diseños | Marca el diseño con estado **`FAILED`** en `custom_designs` (guarda el `code` y el `message`). El encargo sigue su curso normal sin propuesta de IA; el artesano puede trabajar solo con la descripción, y se puede ofrecer "reintentar". |
| Diseños con `content_rejected` | También `FAILED`, pero muestra el `message` al cliente para que cambie la descripción. No reintentar automáticamente. |
| Recomendaciones | Usa las reglas actuales del backend (las que ya usa `DisabledAiClient`). |
| Precio sugerido | No muestres sugerencia (o usa la regla actual). Con `not_enough_data` explica que aún no hay suficientes piezas parecidas. |

Recomendaciones:

- Genera los diseños de forma **asíncrona** (`@Async` o una cola): estado `PENDING` → llamada a
  la IA → `COMPLETED` o `FAILED`. Así el usuario no espera hasta 120 s con la petición abierta.
- No reintentes en bucle: cada imagen real cuesta dinero. Como mucho un reintento manual.
- Registra el `code`, nunca el `AI_SERVICE_KEY`.

## 5. Dónde guardar las imágenes en base64

El servicio de IA **no guarda nada**: devuelve cada imagen en `images[i].image_base64`.

1. Decodifica: `byte[] png = Base64.getDecoder().decode(image.imageBase64());`
2. Súbela al mismo almacenamiento que ya usan las fotos de las obras (por ejemplo, Cloudinary,
   S3 o Supabase Storage), con un nombre como `designs/{requestId}/{uuid}.png` y `image/png`.
3. Guarda en `custom_designs` la **URL** resultante, junto con `provider`, `model` y `prompt`
   (sirve para auditar y para la sustentación).
4. **No guardes el base64 en PostgreSQL**: una imagen de 1024×1024 pesa más de 1 MB en base64.

## 6. Pruebas sin costo

- Con `IMAGE_PROVIDER=fake` y `TEXT_PROVIDER=none` en el servicio de IA, todo funciona sin
  OpenAI: las imágenes son dibujos simples y el precio sale solo de comparables.
- Para pruebas del backend, simula el servicio con `MockRestServiceServer` o WireMock usando los
  JSON de este documento.
- Documentación interactiva del servicio: `<AI_SERVICE_URL>/docs`.

## 7. Render: el servicio "duerme"

En el plan gratis, Render apaga el servicio tras unos 15 minutos sin uso. La primera llamada
después tarda cerca de un minuto mientras arranca, así que puede superar el timeout de 10 s de
recomendaciones y precio.

- Es un fallo esperado: aplica la sección 4 (reglas fijas).
- Opcional: al iniciar sesión un usuario o al abrir el formulario de encargo, haz un
  `GET /health` sin esperar respuesta para "despertar" el servicio antes de necesitarlo.
