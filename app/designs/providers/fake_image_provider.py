"""Free, offline image provider for development and tests.

Pattern: **Adapter**. Adapts Pillow drawing to the ``ImageProvider`` interface. The output
is deterministic: the same request always produces the same image, so it can be tested and
used while developing without paying for OpenAI. It honours the configured format (webp,
jpeg or png), so the backend receives the same kind of image as in production.
"""

import base64
import io

from PIL import Image, ImageDraw

from app.core.text import normalize_code
from app.designs.image_format import MIME_TYPES, ImageFormat
from app.designs.providers.image_provider import ImageProvider
from app.schemas.designs import DesignRequest, GeneratedImage

IMAGE_SIZE = 512
BACKGROUND = "#F3EBDD"
OUTLINE = "#2B1D14"
# Typical Mopa-Mopa colours, used when the request has none.
DEFAULT_PALETTE = ["#B3261E", "#1E6B3A", "#E3A72F", "#1F3A93"]
ROUND_SHAPES = ("bandeja", "plato", "totuma", "mate", "jarron", "florero", "cuenco")
BOX_SHAPES = ("caja", "cofre", "baul", "joyero", "marco", "cuadro", "tabla")


class FakeImageProvider(ImageProvider):
    name = "fake"

    def __init__(self, image_format: ImageFormat = "png", compression: int = 80) -> None:
        self._format = image_format
        self._compression = compression

    @property
    def model(self) -> str:
        return "fake-pillow"

    def generate(self, prompt: str, request: DesignRequest, count: int) -> list[GeneratedImage]:
        palette = [color.hex for color in request.colors] or DEFAULT_PALETTE
        shape = self._shape_kind(request.shape)
        return [
            GeneratedImage(
                image_base64=self._encode(
                    self._draw(shape, palette, len(request.motifs), variant)
                ),
                mime_type=MIME_TYPES[self._format],
            )
            for variant in range(count)
        ]

    @staticmethod
    def _shape_kind(shape: str) -> str:
        code = normalize_code(shape)
        if any(word in code for word in ROUND_SHAPES):
            return "round"
        if any(word in code for word in BOX_SHAPES):
            return "box"
        return "rounded"

    def _encode(self, image: Image.Image) -> str:
        buffer = io.BytesIO()
        if self._format == "png":
            image.save(buffer, format="PNG")
        else:
            image.save(buffer, format=self._format.upper(), quality=self._compression)
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    @staticmethod
    def _draw(shape: str, palette: list[str], motif_count: int, variant: int) -> Image.Image:
        # Each variant rotates the colour order so several images differ from each other.
        colors = palette[variant % len(palette) :] + palette[: variant % len(palette)]
        image = Image.new("RGB", (IMAGE_SIZE, IMAGE_SIZE), BACKGROUND)
        draw = ImageDraw.Draw(image)

        margin = 64
        bands = max(len(colors), 3)
        step = (IMAGE_SIZE // 2 - margin) // (bands + 1)
        for band in range(bands):
            inset = margin + band * step
            box = (inset, inset, IMAGE_SIZE - inset, IMAGE_SIZE - inset)
            fill = colors[band % len(colors)]
            if shape == "round":
                draw.ellipse(box, fill=fill, outline=OUTLINE, width=3)
            elif shape == "box":
                draw.rectangle(box, fill=fill, outline=OUTLINE, width=3)
            else:
                draw.rounded_rectangle(box, radius=40, fill=fill, outline=OUTLINE, width=3)

        # Motifs never use the colour of the inner band, so they stay visible.
        inner = colors[(bands - 1) % len(colors)]
        motif_colors = [color for color in colors if color != inner] or [OUTLINE]
        center = IMAGE_SIZE // 2
        for index in range(min(motif_count, 8)):
            offset = (index - (min(motif_count, 8) - 1) / 2) * 28
            x = center + offset
            diamond = [(x, center - 14), (x + 10, center), (x, center + 14), (x - 10, center)]
            draw.polygon(diamond, fill=motif_colors[index % len(motif_colors)], outline=OUTLINE)
        return image
