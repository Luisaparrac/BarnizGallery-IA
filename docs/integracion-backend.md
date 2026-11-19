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
| `AI_SERVICE_URL` | `https://barnizgallery-ia.onrender.com` | URL base del servicio, sin `/` final |
| `AI_SERVICE_KEY` | (secreta) | La misma `AI_SERVICE_KEY` configurada en el servicio de IA |

Nunca las subas al repositorio; van en el `.env` local y en el panel de Render.

```properties
# application.properties
ai.service.url=${AI_SERVICE_URL:}
ai.service.key=${AI_SERVICE_KEY:}
```

Si `AI_SERVICE_URL` está vacía, se usa `DisabledAiServiceGateway` y el backend sigue con sus
reglas fijas (ver sección 3).

## 2. Reglas generales del contrato (versión 1.1)

- **Autenticación:** todas las rutas, menos `/health`, exigen el header
  `X-API-Key: <AI_SERVICE_KEY>`. Si falta o es incorrecta, la respuesta es `401`.
- **JSON en `snake_case`.** Con Jackson usa `@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)`
  en los DTO.
- **Códigos de texto, no ids:** recomendaciones y precio usan códigos como `"rojo"`, `"colibri"`,
  `"bandeja"`. Sirven los tags de texto actuales y luego los códigos de los catálogos de la v2.
  El servicio los normaliza (minúsculas, sin tildes, sin espacios extra): `"Colibrí"` = `"colibri"`.
- **`X-Request-ID`:** envía uno por llamada (hasta 64 caracteres `A-Z a-z 0-9 . _ -`, por
  ejemplo `pedido-42-intento-1`). El servicio lo devuelve y lo pone en todos sus logs; si no
  lo envías, genera uno. Regístralo en tus logs para seguir una llamada de punta a punta.
- **Límites:** máximo `RATE_LIMIT_PER_MINUTE` (20) llamadas por minuto por clave e IP y cuerpos
  de hasta 1 MB. Las respuestas `429` traen `Retry-After` (segundos).
- **Errores** con la forma `{"code": "...", "message": "..."}`. El `message` está en español y se
  puede mostrar; decide siempre por el `code`:

| HTTP | `code` | Significado | Qué hace el backend |
|---|---|---|---|
| 400 | `invalid_request` | El JSON no cumple el contrato | Es un error del backend: registrarlo y corregir |
| 400 | `content_rejected` | OpenAI rechazó el contenido del encargo | Mostrar al cliente que cambie la descripción |
| 413 | `invalid_request` | Cuerpo de más de 1 MB | Enviar menos candidatos o comparables |
| 429 | `rate_limited` | Más de 20 llamadas por minuto | Reglas fijas; no reintentar antes de `Retry-After` |
| 429 | `budget_exceeded` | Se acabó el cupo diario de imágenes (30) | Diseño `FAILED`; reintentar al día siguiente |
| 401 | `unauthorized` | Falta `X-API-Key` o no es válida | Revisar `AI_SERVICE_KEY` |
| 422 | `not_enough_data` | Pocos datos (precio con menos de 3 comparables) | No sugerir precio |
| 502 | `provider_error` | OpenAI falló | Usar las reglas fijas; se puede reintentar más tarde |
| 503 | `feature_disabled` | La función no está activada en el servicio | Usar las reglas fijas |
| 504 | `provider_timeout` | OpenAI tardó demasiado | Usar las reglas fijas; se puede reintentar más tarde |

### `GET /health`

Sin clave. Útil para despertar el servicio en Render (ver sección 7).

```json
{"status": "ok", "version": "1.1.0", "image_provider": "fake", "text_provider": "none",
 "commit": "883692f..."}
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
  "images": [{"image_base64": "UklGRl...", "mime_type": "image/webp",
              "composition": null, "prompt": "<prompt de esta imagen>"}]
}
```

- **Formato:** por defecto `image/webp` (también puede ser `image/jpeg` o `image/png`, según
  `OPENAI_IMAGE_FORMAT`). Usa siempre `mime_type`, nunca supongas PNG.
- **Variaciones:** con `count: 2` cada imagen trae `composition` (`top`, `three_quarter`,
  `detail`) y su propio `prompt`. El `prompt` de arriba es el de la primera imagen.
- **Moderación:** con OpenAI, el texto del cliente se revisa antes de generar; si se rechaza
  responde `400 content_rejected` sin gastar.
- **Cupo diario:** `429 budget_exceeded` cuando se acaban las imágenes del día.

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
                 "motifs": ["colibri"], "budget": true},
     "explanation": "Coincide con lo que te gusta: los colores rojo y amarillo, la forma bandeja, el estilo tradicional y la figura colibri. Está dentro de tu presupuesto."}
  ]
}
```

- **`explanation`:** frase corta en español lista para mostrar.
- **Diversidad:** el orden evita que un solo taller (`store_id`) llene la lista (MMR). Por eso
  el orden no siempre coincide con `score`: `score` es la relevancia.

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
 "method": "comparables", "confidence": "medium",
 "explanation": "Basado en 6 piezas parecidas, 3 ya vendidas, con un parecido promedio del 100%. Se descartaron 1 precio atípico. ..."}
```

- `method`: `comparables`, o `comparables+llm` si el servicio tiene modelo de texto activado. El
  modelo de texto solo puede mover el precio **dentro** del rango.
- Con menos de 3 comparables en la moneda pedida, haya o no modelo de texto:
  `422 not_enough_data`. **El servicio nunca inventa un precio.**
- Si el modelo de texto falla, responde igual con `method: "comparables"`.
- **Precios atípicos:** se descartan con la regla IQR (por ejemplo, 9500 entre precios de 100).
- **`confidence`:** `high` (8+ comparables con 70 %+ de parecido), `medium` (5+ y 50 %+) o
  `low`. Con `low`, muéstralo como una referencia débil.

### `GET /v1/metrics`

Con `X-API-Key`. Contadores por ruta, latencia, imágenes del día y costo estimado de OpenAI.
Útil para revisar el gasto; se reinicia cuando Render reinicia el servicio.
- Es una **sugerencia** para el artesano: muéstrala como tal y deja que él decida.

## 3. Cliente del servicio de IA en Spring (Adapter)

### Qué se queda igual y qué es nuevo

| Pieza | Paquete | Estado |
|---|---|---|
| `AiTextClient` (`complete(systemPrompt, userPrompt)`, `isEnabled()`) | `patterns.adapter` | **No se toca** |
| `DisabledAiClient` | `patterns.adapter` | **No se toca** (sigue con su `@Component`) |
| `AiStrategy` | `patterns.strategy` | **No se toca** |
| `HybridStrategy` (`"hybrid"`, la de por defecto) | `patterns.strategy` | **No se toca**; es el respaldo de la nueva estrategia |
| `AiServiceGateway` | `patterns.adapter` | **Nueva** interfaz para este servicio |
| `AiServiceClient` | `patterns.adapter` | **Nueva**: implementa `AiServiceGateway` con `RestClient` |
| `DisabledAiServiceGateway` | `patterns.adapter` | **Nueva**: se usa cuando no hay `AI_SERVICE_URL` |
| `AiServiceStrategy` (`"ai-service"`) | `patterns.strategy` | **Nueva** estrategia de recomendación |
| `AiFacade.suggestBasePrice(Artwork)` | `patterns.facade` | Usa el gateway y deja el método actual como respaldo |
| `AiFacade.isAiEnabled()` | `patterns.facade` | `true` si `AiTextClient` **o** `AiServiceGateway` están disponibles |

Todos los paquetes cuelgan de `com.barnizgallery.backend`.

`AiTextClient` es para texto libre (`complete`), y este servicio no tiene texto libre: expone
diseños, recomendaciones y precio sugerido. Por eso el servicio de IA tiene **su propia
interfaz** y no comparte ninguna con `AiTextClient`. Lo que hoy usa `complete()`
(`AiFacade.assessWithAi` para las pujas y `AiStrategy`) sigue igual. Las pujas no van en esta
entrega.

> **Nombres de los DTO:** todos los DTO del servicio de IA llevan el prefijo `Ai`
> (`AiRecommendationResponse`, `AiPriceSuggestion`…) para no chocar con los del backend; en
> particular, `RecommendationResult` ya es el record de salas del backend.
>
> Los nombres que no están en la tabla de arriba (`ArtworkRepository`, `toProfile`,
> `comparablesFor`, campos de `Visitor` y `Artwork`…) son de ejemplo: cámbialos por los reales.

### La interfaz (Adapter, interfaz objetivo)

```java
package com.barnizgallery.backend.patterns.adapter;

/** Funciones del servicio de IA de MUSEO. */
public interface AiServiceGateway {

    /** false cuando no hay AI_SERVICE_URL: el backend usa sus reglas fijas. */
    boolean isAvailable();

    AiPriceSuggestion suggestPrice(AiPricingRequest request);

    AiRecommendationResponse recommend(AiRecommendationRequest request);

    AiDesignResponse generateDesigns(AiDesignRequest request);
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
    public AiPriceSuggestion suggestPrice(AiPricingRequest request) {
        return post(quick, "/v1/pricing/suggest", request, AiPriceSuggestion.class);
    }

    @Override
    public AiRecommendationResponse recommend(AiRecommendationRequest request) {
        return post(quick, "/v1/recommendations", request, AiRecommendationResponse.class);
    }

    @Override
    public AiDesignResponse generateDesigns(AiDesignRequest request) {
        return post(designs, "/v1/designs", request, AiDesignResponse.class);
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
    public AiPriceSuggestion suggestPrice(AiPricingRequest request) {
        throw disabled();
    }

    @Override
    public AiRecommendationResponse recommend(AiRecommendationRequest request) {
        throw disabled();
    }

    @Override
    public AiDesignResponse generateDesigns(AiDesignRequest request) {
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

### Precio: `AiFacade.suggestBasePrice(Artwork)` e `isAiEnabled()`

`suggestBasePrice` sigue devolviendo `Optional<BigDecimal>`. Primero intenta con el gateway; si
no está disponible o falla (`not_enough_data`, error o timeout), usa **el método actual con
`aiClient.complete`**, que se queda como respaldo (aquí renombrado a
`suggestBasePriceWithTextClient`).

```java
package com.barnizgallery.backend.patterns.facade;

@Service
public class AiFacade {

    private static final Logger log = LoggerFactory.getLogger(AiFacade.class);

    private final AiTextClient aiClient;          // como hoy (assessWithAi y el respaldo de precio)
    private final AiServiceGateway aiService;     // nuevo

    public AiFacade(AiTextClient aiClient, AiServiceGateway aiService) {
        this.aiClient = aiClient;
        this.aiService = aiService;
    }

    /** La IA está activa si cualquiera de los dos clientes lo está. */
    public boolean isAiEnabled() {
        return aiClient.isEnabled() || aiService.isAvailable();
    }

    public Optional<BigDecimal> suggestBasePrice(Artwork artwork) {
        if (aiService.isAvailable()) {
            try {
                AiPriceSuggestion suggestion =
                        aiService.suggestPrice(toPricingRequest(artwork, comparablesFor(artwork)));
                return Optional.of(BigDecimal.valueOf(suggestion.suggestedPrice()));
            } catch (AiServiceException | ResourceAccessException e) {
                log.info("Precio sin servicio de IA: {}", e.getMessage());
            }
        }
        return aiClient.isEnabled() ? suggestBasePriceWithTextClient(artwork) : Optional.empty();
    }

    /** El método actual, sin cambios: usa aiClient.complete(...). */
    private Optional<BigDecimal> suggestBasePriceWithTextClient(Artwork artwork) {
        // ... código de hoy ...
    }
}
```

> **Importante — `isAiEnabled()`:** `PricingService.suggestedPrice` lanza
> `FeatureDisabledException` si `!aiFacade.isAiEnabled()`, y hoy `isAiEnabled()` solo mira el
> `AiTextClient`. Si no se cambia como arriba (`aiClient.isEnabled() || aiService.isAvailable()`),
> con el servicio de IA configurado pero `DisabledAiClient` activo, **el precio sugerido nunca
> llegaría a usar la IA**: `PricingService` cortaría antes con `FeatureDisabledException`.
>
> Revisa también los demás usos de `isAiEnabled()`: si alguno depende solo de `complete()` (por
> ejemplo, las pujas con `assessWithAi`), que pregunte por `aiClient.isEnabled()` y no por
> `isAiEnabled()`.

`toPricingRequest` arma el JSON de la sección 2 (`piece` con los códigos de forma, estilo,
colores y figuras, medidas y horas; `comparables` con obras parecidas que tengan precio, y si se
vendieron; y la moneda). El servicio necesita **al menos 3 comparables en la misma moneda**; si
no, responde `not_enough_data` y se usa el respaldo.

### Recomendaciones: estrategia `"ai-service"` por salas

El backend recomienda **salas**, pero el servicio de IA puntúa **obras**. La nueva estrategia
pide la puntuación de las obras disponibles y la agrega por sala:

1. Envía al servicio las obras disponibles como `candidates` (con el código de su forma, estilo,
   colores y figuras) y el perfil e interacciones del `Visitor`. Pide `limit: 100` (el máximo),
   porque se necesitan puntuaciones de todas las obras posibles para sumar por sala.
2. Por cada sala, **suma** el `score` de sus obras pasado de 0..1 a 0..100. Si la sala con más
   puntos pasa de 100, reescala todas para que esa quede en 100: así se respeta el rango 0..100
   de `RecommendationResult` sin perder el orden.
3. Arma el `reason` con los motivos (`reasons`) más repetidos en las obras de la sala.
4. Si el gateway no está disponible, falla o no hay obras, delega en `HybridStrategy`.

Se registra sola en `RecommendationStrategyResolver` porque devuelve `name() = "ai-service"`.
`AiStrategy` no se toca.

```java
package com.barnizgallery.backend.patterns.strategy;

@Component
public class AiServiceStrategy implements RecommendationStrategy {

    private static final Logger log = LoggerFactory.getLogger(AiServiceStrategy.class);
    private static final int MAX_CANDIDATES = 100;

    private final AiServiceGateway aiService;
    private final HybridStrategy fallback;
    private final ArtworkRepository artworks;   // ejemplo: de donde salen las obras disponibles

    public AiServiceStrategy(
            AiServiceGateway aiService, HybridStrategy fallback, ArtworkRepository artworks) {
        this.aiService = aiService;
        this.fallback = fallback;
        this.artworks = artworks;
    }

    @Override
    public String name() {
        return "ai-service";
    }

    @Override
    public List<RecommendationResult> recommend(Visitor visitor) {
        if (!aiService.isAvailable()) {
            return fallback.recommend(visitor);
        }
        List<Artwork> available = artworks.findAvailable();
        if (available.isEmpty()) {
            return fallback.recommend(visitor);
        }
        try {
            var request = new AiRecommendationRequest(
                    toProfile(visitor), toInteractions(visitor),
                    available.stream().map(AiServiceStrategy::toCandidate).toList(),
                    MAX_CANDIDATES);
            return byRoom(aiService.recommend(request).items(), available);
        } catch (AiServiceException | ResourceAccessException e) {
            log.warn("Recomendaciones sin servicio de IA: {}", e.getMessage());
            return fallback.recommend(visitor);
        }
    }

    /** Suma por sala los scores de sus obras (0..1 → 0..100) y arma el motivo. */
    private static List<RecommendationResult> byRoom(
            List<AiRecommendationItem> items, List<Artwork> available) {
        Map<Long, Integer> roomOfArtwork = available.stream()
                .collect(Collectors.toMap(Artwork::getId, Artwork::getRoomId));
        Map<Integer, Double> points = new HashMap<>();
        Map<Integer, List<AiRecommendationReasons>> reasons = new HashMap<>();
        for (AiRecommendationItem item : items) {
            Integer roomId = roomOfArtwork.get(item.artworkId());
            if (roomId == null || item.score() <= 0) {
                continue;
            }
            points.merge(roomId, item.score() * 100, Double::sum);
            reasons.computeIfAbsent(roomId, id -> new ArrayList<>()).add(item.reasons());
        }
        double top = points.values().stream().mapToDouble(Double::doubleValue).max().orElse(0);
        double scale = top > 100 ? 100 / top : 1;

        return points.entrySet().stream()
                .sorted(Map.Entry.<Integer, Double>comparingByValue().reversed()
                        .thenComparing(Map.Entry.comparingByKey()))
                .map(e -> RecommendationResult.of(
                        e.getKey(), e.getValue() * scale, reasonText(reasons.get(e.getKey()))))
                .toList();
    }

    /** Ejemplo: "Colores: rojo, amarillo. Figuras: colibri. Formas y estilos que te gustan." */
    private static String reasonText(List<AiRecommendationReasons> reasons) {
        var parts = new ArrayList<String>();
        var colors = mostFrequent(reasons.stream().flatMap(r -> r.colors().stream()), 3);
        var motifs = mostFrequent(reasons.stream().flatMap(r -> r.motifs().stream()), 3);
        if (!colors.isEmpty()) parts.add("Colores: " + String.join(", ", colors) + ".");
        if (!motifs.isEmpty()) parts.add("Figuras: " + String.join(", ", motifs) + ".");
        if (reasons.stream().anyMatch(r -> r.shape() || r.style())) {
            parts.add("Formas y estilos que te gustan.");
        }
        if (reasons.stream().anyMatch(r -> Boolean.TRUE.equals(r.budget()))) {
            parts.add("Obras dentro de tu presupuesto.");
        }
        return parts.isEmpty() ? "Obras populares en la galería." : String.join(" ", parts);
    }

    private static List<String> mostFrequent(Stream<String> codes, int max) {
        return codes.collect(Collectors.groupingBy(c -> c, LinkedHashMap::new, Collectors.counting()))
                .entrySet().stream()
                .sorted(Map.Entry.<String, Long>comparingByValue().reversed())
                .limit(max)
                .map(Map.Entry::getKey)
                .toList();
    }
}
```

Notas:

- Los códigos (`colors`, `motifs`) llegan normalizados (`colibri`, sin tilde). Si quieres
  mostrarlos con tildes, tradúcelos con los nombres de los tags o catálogos del backend.
- Con `strategy: "popular"` (visitante sin gustos ni interacciones) las obras traen `reasons`
  vacíos: el motivo queda en "Obras populares en la galería.".
- Si hay más de 100 obras disponibles, solo cuentan las 100 mejor puntuadas.

### Diseños

El servicio de encargos llama a `aiService.generateDesigns(...)` solo si
`aiService.isAvailable()`, de forma asíncrona (ver sección 4). Si no está disponible, el encargo
sigue sin propuesta de IA.

### DTO

Todos con `@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)`, siguiendo los JSON
de la sección 2:

```java
public record AiError(String code, String message) {}

// Diseños
public record AiDesignRequest(Integer requestId, String title, String description, String shape,
        String style, List<AiDesignColor> colors, List<String> motifs, String sizeNotes,
        String language, Integer count) {}
public record AiDesignColor(String name, String hex) {}
public record AiDesignResponse(String provider, String model, String prompt,
        List<AiDesignImage> images) {}
public record AiDesignImage(String imageBase64, String mimeType, String composition,
        String prompt) {}

// Recomendaciones
public record AiRecommendationRequest(AiTasteProfile profile, List<AiInteraction> interactions,
        List<AiCandidate> candidates, Integer limit) {}
public record AiRecommendationResponse(String strategy, List<AiRecommendationItem> items) {}
public record AiRecommendationItem(Long artworkId, Long storeId, double score,
        AiRecommendationReasons reasons, String explanation) {}
public record AiRecommendationReasons(List<String> colors, boolean shape, boolean style,
        List<String> motifs, Boolean budget) {}

// Precio
public record AiPriceSuggestion(double suggestedPrice, double minPrice, double maxPrice,
        String currency, String method, String explanation, String confidence) {}
```

`AiTasteProfile`, `AiInteraction`, `AiCandidate` y `AiPricingRequest` siguen igual los campos de
la sección 2. `budget` en `AiRecommendationReasons` es `Boolean` porque puede llegar `null`.

`AiServiceException` es una excepción propia (`RuntimeException`) con `status`, `code` y
`message`. Los timeouts y errores de red llegan como `ResourceAccessException`.

## 4. Qué hacer si la IA falla

La regla: **un fallo de la IA nunca rompe el flujo del usuario.**

| Función | Si falla (`5xx`, timeout, `ResourceAccessException`) |
|---|---|
| Diseños | Marca el diseño con estado **`FAILED`** en `custom_designs` (guarda el `code` y el `message`). El encargo sigue su curso normal sin propuesta de IA; el artesano puede trabajar solo con la descripción, y se puede ofrecer "reintentar". |
| Diseños con `content_rejected` | También `FAILED`, pero muestra el `message` al cliente para que cambie la descripción. No reintentar automáticamente. |
| Diseños con `budget_exceeded` (429) | `FAILED` con el mensaje; reintentar al día siguiente. |
| Cualquier `rate_limited` (429) | Reglas fijas; no reintentar antes de `Retry-After`. |
| Recomendaciones | La estrategia `"ai-service"` delega en `HybridStrategy`. |
| Precio sugerido | `AiFacade.suggestBasePrice` usa el método actual con `aiClient.complete` y, si tampoco hay, devuelve `Optional.empty()`. |

Recomendaciones:

- Genera los diseños de forma **asíncrona** (`@Async` o una cola): estado `PENDING` → llamada a
  la IA → `COMPLETED` o `FAILED`. Así el usuario no espera hasta 120 s con la petición abierta.
- No reintentes en bucle: cada imagen real cuesta dinero. Como mucho un reintento manual.
- Registra el `code`, nunca el `AI_SERVICE_KEY`.

## 5. Dónde guardar las imágenes en base64

El servicio de IA **no guarda nada**: devuelve cada imagen en `images[i].image_base64`.

1. Decodifica: `byte[] bytes = Base64.getDecoder().decode(image.imageBase64());`
2. Súbela al mismo almacenamiento que ya usan las fotos de las obras (por ejemplo, Cloudinary,
   S3 o Supabase Storage) con la extensión y el `Content-Type` de `mime_type`: `image/webp` →
   `designs/{requestId}/{uuid}.webp`, `image/jpeg` → `.jpg`, `image/png` → `.png`.
3. Guarda en `custom_designs` la **URL** resultante, junto con `provider`, `model` y `prompt`
   (sirve para auditar y para la sustentación).
4. **No guardes el base64 en PostgreSQL**: aunque en webp pesa mucho menos que en PNG, sigue
   siendo un archivo; guarda solo la URL.

## 6. Pruebas sin costo

- Con `IMAGE_PROVIDER=fake` y `TEXT_PROVIDER=none` en el servicio de IA, todo funciona sin
  OpenAI: las imágenes son dibujos simples y el precio sale solo de comparables.
- Para pruebas del backend, simula el servicio con `MockRestServiceServer` o WireMock usando los
  JSON de este documento.
- Documentación interactiva con ejemplos: `<AI_SERVICE_URL>/docs` (en producción puede estar
  oculta con `DOCS_ENABLED=false`).
- Para revisar el despliegue sin gastar: `AI_SERVICE_KEY=... python scripts/smoke_test.py`.

## 7. Render: el servicio "duerme"

En el plan gratis, Render apaga el servicio tras unos 15 minutos sin uso. La primera llamada
después tarda cerca de un minuto mientras arranca, así que puede superar el timeout de 10 s de
recomendaciones y precio.

- Es un fallo esperado: aplica la sección 4 (reglas fijas).
- Opcional: al iniciar sesión un usuario o al abrir el formulario de encargo, haz un
  `GET /health` sin esperar respuesta para "despertar" el servicio antes de necesitarlo.
