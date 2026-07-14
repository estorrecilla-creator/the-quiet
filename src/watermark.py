"""
watermark.py
Genera una pegatina PNG transparente (logo + nombre del tema) pequeña y
discreta, para quemarla en la esquina superior izquierda de los vídeos con
ffmpeg. Se renderiza con PIL (igual que thumbnail_template.py) en vez de
con el filtro `drawtext` de ffmpeg, para no depender del escapado de texto
de ffmpeg (frágil con acentos, comillas, dos puntos...).

Se coloca siempre arriba a la izquierda a propósito:
  - la letra sincronizada y la barra de forma de onda ocupan la franja
    inferior, casi a todo lo ancho -> abajo está descartado.
  - el watermark nativo de canal de YouTube (logo, automático en los
    vídeos largos vía la API, ver src/youtube_watermark.py) aparece
    arriba a la derecha -> para no pisarlo, el nuestro va a la izquierda.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT = str(Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Jura-Medium.ttf")


def make_watermark_sticker(
    out_path: str,
    track_title: str = None,
    logo_path: str = None,
    height_px: int = 90,
    opacity: float = 0.65,
    font_path: str = DEFAULT_FONT,
    gap_px: int = 14,
) -> str:
    """
    Genera una pegatina RGBA de altura `height_px` con el logo (si se
    pasa `logo_path`, un PNG con transparencia) seguido del nombre del
    tema (si se pasa `track_title`), en blanco con borde negro fino para
    que se lea sobre cualquier fondo. Al menos uno de los dos tiene que
    venir. La opacidad se aplica al conjunto (logo + texto) para que sea
    discreta, "nada llamativa".
    """
    if not track_title and not logo_path:
        raise ValueError("Hace falta track_title, logo_path, o ambos.")

    logo_img = None
    logo_w = 0
    if logo_path:
        logo_img = Image.open(logo_path).convert("RGBA")
        aspect = logo_img.width / logo_img.height
        logo_w = round(height_px * aspect)
        logo_img = logo_img.resize((logo_w, height_px), Image.LANCZOS)

    font = ImageFont.truetype(font_path, round(height_px * 0.55)) if track_title else None
    text_w = 0
    text_bbox = None
    if track_title:
        measure_img = Image.new("RGBA", (10, 10))
        measure_draw = ImageDraw.Draw(measure_img)
        text_bbox = measure_draw.textbbox((0, 0), track_title, font=font, stroke_width=2)
        text_w = text_bbox[2] - text_bbox[0]

    gap = gap_px if (logo_img and track_title) else 0
    canvas_w = logo_w + gap + text_w
    canvas = Image.new("RGBA", (max(canvas_w, 1), height_px), (0, 0, 0, 0))

    if logo_img:
        canvas.alpha_composite(logo_img, (0, 0))

    if track_title:
        draw = ImageDraw.Draw(canvas)
        text_h = text_bbox[3] - text_bbox[1]
        x = logo_w + gap - text_bbox[0]
        y = (height_px - text_h) / 2 - text_bbox[1]
        draw.text(
            (x, y), track_title, font=font, fill=(255, 255, 255, 255),
            stroke_width=2, stroke_fill=(0, 0, 0, 255),
        )

    if opacity < 1.0:
        r, g, b, a = canvas.split()
        a = a.point(lambda v: round(v * opacity))
        canvas = Image.merge("RGBA", (r, g, b, a))

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    return out_path


def watermark_overlay_filter(base_label: str, out_label: str, wm_input_idx: int, w: int, margin_ratio: float = 0.03) -> str:
    """
    Fragmento de filtro que superpone la pegatina (ya cargada como input
    `wm_input_idx` con `-loop 1 -i sticker.png`) sobre `base_label`, en la
    esquina superior izquierda.
    """
    margin = round(w * margin_ratio)
    return f"[{wm_input_idx}:v]format=rgba[wmsticker];[{base_label}][wmsticker]overlay=x={margin}:y={margin}[{out_label}]"


if __name__ == "__main__":
    import sys

    title = sys.argv[1] if len(sys.argv) > 1 else "Nombre del tema"
    logo = sys.argv[2] if len(sys.argv) > 2 else None
    out = sys.argv[3] if len(sys.argv) > 3 else "watermark_preview.png"
    make_watermark_sticker(out, track_title=title, logo_path=logo)
    print(f"Generada: {out}")
