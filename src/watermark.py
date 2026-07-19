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

import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.color_match import _get_video_duration

DEFAULT_FONT = str(Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Jura-Medium.ttf")


def _strip_checkerboard_background(
    img: Image.Image, min_coverage: float = 0.35, gray_tolerance: int = 10,
    cluster_tolerance: int = 20, quantize_step: int = 8,
) -> Image.Image:
    """
    Algunas herramientas "queman" el patrón de cuadrícula de transparencia
    como píxeles reales de la imagen en vez de guardar transparencia de
    verdad. Detecta ese patrón — dos colores NEUTROS (grises, blanco o
    negro: R≈G≈B en cada uno, no coloreados) que dominan la imagen a
    partes casi iguales, como corresponde a un tablero de cuadros que
    alterna dos tonos — y los vuelve transparentes.

    Importante: los dos colores del tablero suelen tener bastante
    contraste ENTRE SÍ (ej. gris claro y blanco) — lo que los distingue
    del contenido real del logo no es que sean parecidos entre ellos,
    sino que cada uno es neutro/sin color y que juntos cubren gran parte
    de la imagen a partes iguales. Si la imagen no tiene esa firma clara
    (ej. ya tenía transparencia real, o el fondo no es un tablero de
    cuadros), la deja tal cual — mejor no tocar nada que arriesgarse a
    borrar parte del logo real por error.

    Un archivo real (sobre todo si pasó por JPG o por cualquier
    reescalado/compresión) casi nunca tiene los dos tonos del tablero
    como colores planos exactos — la compresión los dispersa en cientos
    de tonos casi iguales. Cuadricular por `quantize_step` reduce esos
    tonos a un puñado de valores, pero un mismo tono real puede caer
    partido en dos cuadrículas contiguas (ej. 251 y 253 con paso 8 caen
    en cubos distintos) — por eso, tras cuadricular, se agrupan además
    por cercanía real (`cluster_tolerance`): se toma el tono más
    frecuente, se suman a él todos los tonos a menos de esa distancia, y
    se repite con el resto, así el recuento total por tono no depende de
    en qué lado del corte de la cuadrícula cayó cada píxel.
    """
    rgba = img.convert("RGBA")
    rgb = np.array(rgba.convert("RGB")).reshape(-1, 3).astype(int)

    quantized = (rgb // quantize_step) * quantize_step + quantize_step // 2
    q_colors, q_counts = np.unique(quantized, axis=0, return_counts=True)

    def _is_neutral(color) -> bool:
        return int(color.max()) - int(color.min()) <= gray_tolerance

    neutral_mask = np.array([_is_neutral(c) for c in q_colors])
    q_colors, q_counts = q_colors[neutral_mask], q_counts[neutral_mask]
    if len(q_colors) < 1:
        return rgba

    order = np.argsort(-q_counts)
    q_colors, q_counts = q_colors[order], q_counts[order]

    clusters = []  # (color_representativo, recuento_total)
    used = np.zeros(len(q_colors), dtype=bool)
    for i in range(len(q_colors)):
        if used[i] or len(clusters) >= 2:
            break
        center = q_colors[i]
        near = (~used) & (np.abs(q_colors - center).max(axis=1) <= cluster_tolerance)
        clusters.append((center, int(q_counts[near].sum())))
        used |= near

    if len(clusters) < 2:
        return rgba

    (top_color, top_count), (second_color, second_count) = clusters[0], clusters[1]
    total_px = rgb.shape[0]

    coverage = (top_count + second_count) / total_px
    balance = min(top_count, second_count) / max(top_count, second_count)

    is_checkerboard = coverage >= min_coverage and balance >= 0.7
    if not is_checkerboard:
        return rgba

    arr = np.array(rgba)
    for color in (top_color, second_color):
        match = (np.abs(rgb - color).max(axis=1) <= cluster_tolerance).reshape(arr.shape[:2])
        arr[match, 3] = 0

    return Image.fromarray(arr, "RGBA")

# Zona de la esquina superior izquierda donde se coloca la pegatina, como
# fracción del ancho/alto del vídeo — más generosa que el tamaño real de la
# pegatina a propósito, para que el brillo medido sea representativo aunque
# la escena se mueva un poco durante el Short.
WATERMARK_REGION_RATIO = (0.35, 0.20)


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
        logo_img = _strip_checkerboard_background(Image.open(logo_path))
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


def _corner_brightness(image: Image.Image, region_ratio=WATERMARK_REGION_RATIO) -> float:
    w, h = image.size
    rw, rh = max(int(w * region_ratio[0]), 1), max(int(h * region_ratio[1]), 1)
    region = np.array(image.convert("L").crop((0, 0, rw, rh)))
    return region.mean() / 255.0


def pick_logo_variant(
    cover_path: str,
    logo_light_path: str = None,
    logo_dark_path: str = None,
    is_video: bool = False,
    sample_frames: int = 3,
    light_threshold: float = 0.5,
) -> str:
    """
    Un logo sin fondo depende del contraste con lo que tenga detrás: elige
    entre `logo_light_path` (logo claro, para fondos oscuros) y
    `logo_dark_path` (logo oscuro, para fondos claros) según el brillo
    medio de la esquina superior izquierda de `cover_path` (la zona donde
    se coloca la marca de agua) — muestreando varios fotogramas repartidos
    si es un clip de vídeo, o el propio fotograma si es una imagen fija.
    Si solo se pasa una variante, se usa esa siempre.
    """
    if logo_light_path and not logo_dark_path:
        return logo_light_path
    if logo_dark_path and not logo_light_path:
        return logo_dark_path
    if not logo_light_path and not logo_dark_path:
        return None

    if is_video:
        duration = _get_video_duration(cover_path)
        values = []
        for i in range(sample_frames):
            t = duration * (i + 0.5) / sample_frames
            frame_path = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", cover_path, "-frames:v", "1", frame_path],
                    capture_output=True,
                )
                values.append(_corner_brightness(Image.open(frame_path)))
            finally:
                if os.path.exists(frame_path):
                    os.remove(frame_path)
        brightness = sum(values) / len(values) if values else 0.5
    else:
        brightness = _corner_brightness(Image.open(cover_path))

    return logo_dark_path if brightness > light_threshold else logo_light_path


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
