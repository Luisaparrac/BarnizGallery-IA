# Integración del backend con el servicio de IA

Guía para la encargada de **BarnizGallery-Backend** (Spring). Explica el contrato del servicio de
IA, cómo conectarlo con `AiServiceGateway` / `AiServiceClient` sin tocar `AiTextClient` ni
`DisabledAiClient`, y qué hacer cuando la IA falla.

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

Si `AI_SERVICE_URL` está vacía, se usa `DisabledAiServiceGateway` y el backend sigue con sus
reglas fijas (ver sección 3).

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
- Con menos de 3 comparables en la moneda pedida, haya o no modelo de texto:
  `422 not_enough_data`. **El servicio nunca inventa un precio.**
- Si el modelo de texto falla, responde igual con `method: "comparables"`.
- Es una **sugerencia** para el artesano: muéstrala como tal y deja que él decida.

## 3. Cliente del servicio de IA en Spring (Adapter)

### Qué se queda igual y qué es nuevo

| Pieza | Paquete | Estado |
|---|---|---|
| `AiTextClient` (`complete(systemPrompt, userPrompt)`, `isEnabled()`) | `com.barnizgallery.backend.patterns.adapter` | **No se toca** |
| `DisabledAiClient` | `com.barnizgallery.backend.patterns.adapter` | **No se toca** (sigue con su `@Component`) |
| `AiStrategy` | (recomendaciones) | **No se toca** |
| `AiServiceGateway` | `com.barnizgallery.backend.patterns.adapter` | **Nueva** interfaz para este servicio |
| `AiServiceClient` | `com.barnizgallery.backend.patterns.adapter` | **Nueva**: implementa `AiServiceGateway` con `RestClient` |
| `DisabledAiServiceGateway` | `com.barnizgallery.backend.patterns.adapter` | **Nueva**: se usa cuando no hay `AI_SERVICE_URL` |
| `AiServiceRecommendationStrategy` (`"ai-service"`) | junto a `AiStrategy` | **Nueva** estrategia en `RecommendationStrategyResolver` |
| `AiFacade.suggestBasePrice` | `com.barnizgallery.backend.patterns.facade` | Usa el gateway si está disponible |

`AiTextClient` es para texto libre (`complete`), y este servicio no tiene texto libre: expone
diseños, recomendaciones y precio sugerido. Por eso el servicio de IA tiene **su propia
interfaz** y no comparte ninguna con `AiTextClient`. Todo lo que hoy usa `complete()`
(`AiFacade.assessWithAi` para las pujas y `AiStrategy`) sigue igual, con `DisabledAiClient` y las
reglas fijas. Las pujas no van en esta entrega.

> En los fragmentos de código, los nombres que no están en esta tabla (DTO, entidades,
> `RecommendationStrategy`, `fixedRulesStrategy`…) son de ejemplo: cámbialos por los que ya tiene
> el backend.

### La interfaz (Adapter, interfaz objetivo)

```java
package com.barnizgallery.backend.patterns.adapter;

/** Funciones del servicio de IA de MUSEO. */
public interface AiServiceGateway {

    /** false cuando no hay AI_SERVICE_URL: el backend usa sus reglas fijas. */
    boolean isAvailable();

    PriceSuggestion suggestPrice(PricingAiRequest request);

    RecommendationResult recommend(RecommendationAiRequest request);

    DesignResult generateDesigns(DesignAiRequest request);
}
```

### La implementación real: `AiServiceClient`

Usa dos `RestClient`: uno con **120 s** de lectura para diseños (generar imágenes tarda) y otro
con **10 s** para recomendaciones y precio. Todos llevan el header `X-API-Key`.

```java
package com.barnizgallery.backend.patterns.adapter;

public class AiServiceClient implements AiServiceGateway {

    private static final Logger log = LoggerFactory.getLogger(AiServiceClient.class);

    private final RestClient designs;   // 120 s
    private final RestClient quick;     // 10 s

    public AiServiceClient(RestClient designs, RestClient quick) {
        this.designs = designs;
        this.quick = quick;
    }

    @Override
    public boolean isAvailable() {
        return true;
    }

    @Override
    public PriceSuggestion suggestPrice(PricingAiRequest request) {
        return post(quick, "/v1/pricing/suggest", request, PriceSuggestion.class);
    }

    @Override
    public RecommendationResult recommend(RecommendationAiRequest request) {
        return post(quick, "/v1/recommendations", request, RecommendationResult.class);
    }

    @Override
    public DesignResult generateDesigns(DesignAiRequest request) {
        return post(designs, "/v1/designs", request, DesignResult.class);
    }

    private static <T> T post(RestClient client, String uri, Object body, Class<T> type) {
        return client.post().uri(uri)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body)
                .retrieve()
                .onStatus(HttpStatusCode::isError, AiServiceClient::throwAiError)
                .body(type);
    }

    private static void throwAiError(HttpRequest req, ClientHttpResponse res) throws IOException {
        var error = new ObjectMapper().readValue(res.getBody(), AiError.class);
        log.warn("Servicio de IA respondió {} {}", res.getStatusCode().value(), error.code());
        throw new AiServiceException(res.getStatusCode().value(), error.code(), error.message());
    }
}
```

### La implementación deshabilitada

```java
package com.barnizgallery.backend.patterns.adapter;

/** Se usa cuando no hay AI_SERVICE_URL. Quien la llame debe revisar isAvailable() antes. */
public class DisabledAiServiceGateway implements AiServiceGateway {

    @Override
    public boolean isAvailable() {
        return false;
    }

    @Override
    public PriceSuggestion suggestPrice(PricingAiRequest request) {
        throw disabled();
    }

    @Override
    public RecommendationResult recommend(RecommendationAiRequest request) {
        throw disabled();
    }

    @Override
    public DesignResult generateDesigns(DesignAiRequest request) {
        throw disabled();
    }

    private static AiServiceException disabled() {
        return new AiServiceException(503, "feature_disabled", "El servicio de IA no está configurado.");
    }
}
```

### Configuración: un solo bean `AiServiceGateway`

```java
package com.barnizgallery.backend.patterns.adapter;

@Configuration
public class AiServiceConfig {

    @Bean
    public AiServiceGateway aiServiceGateway(
            @Value("${ai.service.url:}") String url,
            @Value("${ai.service.key:}") String key) {
        if (url.isBlank()) {
            return new DisabledAiServiceGateway();
        }
        if (key.isBlank()) {
            throw new IllegalStateException("Falta AI_SERVICE_KEY para usar el servicio de IA");
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

`AiServiceGateway` y `AiTextClient` son tipos distintos, así que no hay ambigüedad entre beans y
`DisabledAiClient` no cambia.

### Precio: `AiFacade.suggestBasePrice`

`AiFacade` recibe además el `AiServiceGateway`. Si está disponible y responde, usa su
sugerencia; si no (deshabilitado, `not_enough_data`, error o timeout), **sigue como hoy**.

```java
package com.barnizgallery.backend.patterns.facade;

@Service
public class AiFacade {

    private final AiTextClient aiTextClient;     // como hoy (pujas: assessWithAi)
    private final AiServiceGateway aiService;    // nuevo

    public AiFacade(AiTextClient aiTextClient, AiServiceGateway aiService) {
        this.aiTextClient = aiTextClient;
        this.aiService = aiService;
    }

    public PriceSuggestionDto suggestBasePrice(Artwork piece, List<Artwork> comparables) {
        if (aiService.isAvailable()) {
            try {
                var request = toPricingRequest(piece, comparables);
                return PriceSuggestionDto.from(aiService.suggestPrice(request));
            } catch (AiServiceException | ResourceAccessException e) {
                log.info("Precio sin servicio de IA: {}", e.getMessage());
            }
        }
        return currentSuggestBasePrice(piece, comparables);   // el código que el método tiene hoy
    }
}
```

### Recomendaciones: estrategia `"ai-service"`

Una estrategia nueva, registrada en `RecommendationStrategyResolver` con el nombre
`"ai-service"`. Implementa la misma interfaz que `AiStrategy` (aquí `RecommendationStrategy`),
pero usa el gateway. **`AiStrategy` no se toca.** Si el gateway no está disponible o falla,
delega en la estrategia de reglas fijas que ya tiene el backend.

```java
@Component
public class AiServiceRecommendationStrategy implements RecommendationStrategy {

    private static final Logger log = LoggerFactory.getLogger(AiServiceRecommendationStrategy.class);

    private final AiServiceGateway aiService;
    private final RecommendationStrategy fallback;   // la estrategia de reglas fijas actual

    public AiServiceRecommendationStrategy(
            AiServiceGateway aiService,
            @Qualifier("fixedRulesStrategy") RecommendationStrategy fallback) {
        this.aiService = aiService;
        this.fallback = fallback;
    }

    @Override
    public String name() {
        return "ai-service";
    }

    @Override
    public List<Long> recommend(Customer customer, List<Artwork> available) {
        if (!aiService.isAvailable()) {
            return fallback.recommend(customer, available);
        }
        try {
            return aiService.recommend(toRequest(customer, available)).items().stream()
                    .map(RecommendationItem::artworkId)
                    .toList();
        } catch (AiServiceException | ResourceAccessException e) {
            log.warn("Recomendaciones sin servicio de IA: {}", e.getMessage());
            return fallback.recommend(customer, available);
        }
    }
}
```

### Diseños

El servicio de encargos llama a `aiService.generateDesigns(...)` solo si
`aiService.isAvailable()`, de forma asíncrona (ver sección 4). Si no está disponible, el encargo
sigue sin propuesta de IA.

### DTO

```java
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record AiError(String code, String message) {}

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record DesignResult(String provider, String model, String prompt, List<DesignImage> images) {}

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record DesignImage(String imageBase64, String mimeType) {}
```

Los demás DTO (`DesignAiRequest`, `RecommendationAiRequest`, `RecommendationResult`,
`PricingAiRequest`, `PriceSuggestion`) siguen los JSON de la sección 2, también con `snake_case`.

`AiServiceException` es una excepción propia (`RuntimeException`) con `status`, `code` y
`message`. Los timeouts y errores de red llegan como `ResourceAccessException`.

## 4. Qué hacer si la IA falla

La regla: **un fallo de la IA nunca rompe el flujo del usuario.**

| Función | Si falla (`5xx`, timeout, `ResourceAccessException`) |
|---|---|
| Diseños | Marca el diseño con estado **`FAILED`** en `custom_designs` (guarda el `code` y el `message`). El encargo sigue su curso normal sin propuesta de IA; el artesano puede trabajar solo con la descripción, y se puede ofrecer "reintentar". |
| Diseños con `content_rejected` | También `FAILED`, pero muestra el `message` al cliente para que cambie la descripción. No reintentar automáticamente. |
| Recomendaciones | La estrategia `"ai-service"` delega en la estrategia de reglas fijas actual. |
| Precio sugerido | `AiFacade.suggestBasePrice` sigue como hoy. Con `not_enough_data` también puedes explicar que aún no hay suficientes piezas parecidas. |

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
