from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


CANVAS_SIZE = (1080, 1080)


def ensure_default_template(path: Path) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")

    # An elegant blue-and-gold overlay; the middle remains transparent for the photo.
    draw.rounded_rectangle((20, 20, 1060, 1060), radius=76, outline=(18, 71, 125, 255), width=42)
    draw.rounded_rectangle((66, 66, 1014, 1014), radius=54, outline=(232, 181, 72, 245), width=12)
    draw.rectangle((0, 0, 1080, 150), fill=(18, 71, 125, 225))
    draw.rectangle((0, 930, 1080, 1080), fill=(18, 71, 125, 225))
    draw.polygon([(0, 150), (260, 150), (0, 330)], fill=(18, 71, 125, 225))
    draw.polygon([(1080, 750), (1080, 930), (820, 930)], fill=(18, 71, 125, 225))

    rng = random.Random(42)
    colors = [(232, 181, 72, 235), (255, 255, 255, 220), (67, 160, 210, 230)]
    for _ in range(52):
        x = rng.choice([rng.randint(40, 230), rng.randint(850, 1040)])
        y = rng.randint(175, 905)
        size = rng.randint(7, 18)
        color = rng.choice(colors)
        draw.ellipse((x - size, y - size, x + size, y + size), fill=color)
    image.save(path, "PNG")
    return path


def validate_overlay(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise ValueError("Шаблон должен быть PNG-файлом")
            rgba = image.convert("RGBA")
            alpha_min, _ = rgba.getchannel("A").getextrema()
            if alpha_min == 255:
                raise ValueError("В PNG нет прозрачных областей (альфа-канала)")
            if rgba.width < 300 or rgba.height < 300:
                raise ValueError("Шаблон слишком маленький; рекомендуемый размер — 1080×1080")
            return rgba.size
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Не удалось прочитать PNG-шаблон") from exc


def render_card(photo_path: Path, overlay_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(overlay_path) as overlay_source:
        overlay = overlay_source.convert("RGBA")
    with Image.open(photo_path) as photo_source:
        photo = ImageOps.exif_transpose(photo_source).convert("RGB")
        fitted = ImageOps.fit(photo, overlay.size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        base = fitted.convert("RGBA")
    result = Image.alpha_composite(base, overlay).convert("RGB")
    result.save(output_path, "JPEG", quality=94, optimize=True)
    return output_path
