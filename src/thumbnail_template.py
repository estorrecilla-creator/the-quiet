"""
thumbnail_template.py
Genera una miniatura de YouTube por tema a partir de una portada de LP
"plantilla" (logo + nombre del grupo + nombre del álbum): tapa el texto
del nombre del álbum con un rectángulo del color de fondo y escribe en su
lugar el título del tema, dejando el resto del diseño (logo, nombre del
grupo) intacto.

Pensado para portadas con fondo sólido/uniforme en la zona del texto (como
"The Hollow Hour": fondo negro liso) — si el fondo no es uniforme, el
tapado se notará.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT = str(Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Jura-Medium.ttf")


def _pick_contrasting_text_color(bg_color) -> tuple:
    """
    Gris claro sobre fondos oscuros, gris oscuro sobre fondos claros —
    luminancia relativa estándar (ITU-R BT.709) para decidir cuál toca,
    en vez de un gris fijo que solo funciona bien sobre fondo negro (como
    "The Hollow Hour", pero no necesariamente el próximo LP).
    """
    r, g, b = bg_color
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (210, 210, 210) if luminance < 128 else (45, 45, 45)


def make_track_thumbnail(
    template_path: str,
    track_title: str,
    out_path: str,
    text_band=(0.85, 0.95),  # (top, bottom) como fracción de la altura
    bg_color=None,  # None = tomarlo de la propia imagen (esquina superior izquierda)
    text_color=None,  # None = elegir automáticamente según el contraste con bg_color
    font_path: str = DEFAULT_FONT,
    max_width_ratio: float = 0.85,
) -> str:
    """
    `template_path`: portada del LP con el logo/nombre de grupo/nombre de
    álbum ya diseñada.
    `track_title`: texto que sustituye al nombre del álbum (el título del
    tema en cuestión).
    `out_path`: dónde guardar la miniatura resultante.
    Devuelve `out_path`.
    """
    img = Image.open(template_path).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    if bg_color is None:
        # Muestrea el color de fondo real de la propia imagen (evita una
        # costura visible si el negro "de verdad" no es (0,0,0) exacto).
        corner = img.crop((0, 0, min(30, w), min(30, h)))
        pixels = list(corner.getdata())
        bg_color = tuple(sum(c) // len(pixels) for c in zip(*pixels))

    if text_color is None:
        text_color = _pick_contrasting_text_color(bg_color)

    top = int(h * text_band[0])
    bottom = int(h * text_band[1])
    draw.rectangle([0, top, w, bottom], fill=bg_color)

    max_width = int(w * max_width_ratio)
    band_height = bottom - top

    font_size = band_height
    font = ImageFont.truetype(font_path, font_size)
    bbox = draw.textbbox((0, 0), track_title, font=font)
    text_w = bbox[2] - bbox[0]
    while text_w > max_width and font_size > 8:
        font_size -= 2
        font = ImageFont.truetype(font_path, font_size)
        bbox = draw.textbbox((0, 0), track_title, font=font)
        text_w = bbox[2] - bbox[0]

    text_h = bbox[3] - bbox[1]
    x = (w - text_w) / 2 - bbox[0]
    y = top + (band_height - text_h) / 2 - bbox[1]
    draw.text((x, y), track_title, font=font, fill=text_color)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, quality=95)
    return out_path


if __name__ == "__main__":
    import sys

    template, title, out = sys.argv[1], sys.argv[2], sys.argv[3]
    make_track_thumbnail(template, title, out)
    print(f"Generada: {out}")
