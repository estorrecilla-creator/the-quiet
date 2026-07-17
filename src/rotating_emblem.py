"""
rotating_emblem.py
Genera un vídeo de fondo en bucle a partir de una miniatura/portada ya
aplanada (sin capas): el anillo exterior (con los 4 puntos) gira en un
sentido, un patrón interior se redibuja y gira en el sentido contrario
por detrás del texto central, y el resto (fondo, títulos, texto central)
se queda fijo.

Por qué se redibuja el patrón interior en vez de recortarlo: en una
imagen ya fusionada (sin capas), las líneas del patrón interior y el
texto central se solapan en los mismos píxeles — no hay forma de saber
qué había "detrás" del texto. Recortar y girar esa zona tal cual dejaría
un hueco visible moviéndose por donde antes tapaba el texto. Redibujarlo
desde cero evita ese defecto: es un patrón completo, sin huecos.

La zona protegida (donde vive el texto central, ej. "IWT") se define con
un rectángulo aproximado, no con el contorno exacto de cada letra — no
hay forma de trazarlo automáticamente sin las capas originales. Puede
quedar algún resto de línea original muy pegado al texto; es un detalle
menor, no una costura que se mueve.

Todos los parámetros de geometría son fracciones del tamaño de la imagen
(0-1), para que valgan a cualquier resolución. Son una estimación visual
de partida — genera un fotograma de prueba con `preview_frame()` sobre la
imagen REAL y ajusta antes de renderizar todos los Shorts.
"""

import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, ImageDraw


@dataclass
class EmblemGeometry:
    center_x_frac: float = 0.500
    center_y_frac: float = 0.478
    ring_outer_r_frac: float = 0.335
    ring_inner_r_frac: float = 0.300
    inner_pattern_r_frac: float = 0.285
    protect_box_frac: tuple = (0.30, 0.335, 0.72, 0.62)  # (x0, y0, x1, y1)
    line_color: tuple = (150, 150, 150)
    line_width: int = 2


def _abs_geometry(geo: EmblemGeometry, size: int):
    cx = geo.center_x_frac * size
    cy = geo.center_y_frac * size
    r_outer = geo.ring_outer_r_frac * size
    r_inner_ring = geo.ring_inner_r_frac * size
    r_inner_pattern = geo.inner_pattern_r_frac * size
    x0, y0, x1, y1 = geo.protect_box_frac
    box = (x0 * size, y0 * size, x1 * size, y1 * size)
    return cx, cy, r_outer, r_inner_ring, r_inner_pattern, box


def draw_inner_pattern(size: int, cx: float, cy: float, radius: float, geo: EmblemGeometry) -> Image.Image:
    """Redibuja el patrón interior (cruz + aspa + círculo fino + marcas)
    como RGBA transparente, centrado en (cx, cy)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color, width = geo.line_color, geo.line_width

    draw.line([(cx, cy - radius), (cx, cy + radius)], fill=color, width=width)
    draw.line([(cx - radius, cy), (cx + radius, cy)], fill=color, width=width)

    d = radius * 0.92
    draw.line([(cx - d, cy - d), (cx + d, cy + d)], fill=color, width=width)
    draw.line([(cx - d, cy + d), (cx + d, cy - d)], fill=color, width=width)

    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=color, width=width)

    draw.line([(cx, cy - radius * 0.55), (cx, cy - radius * 0.45)], fill=color, width=width)

    y0 = cy + radius * 0.55
    draw.line([(cx - radius * 0.08, y0), (cx - radius * 0.08, y0 + radius * 0.12)], fill=color, width=width)
    draw.line([(cx + radius * 0.08, y0), (cx + radius * 0.08, y0 + radius * 0.12)], fill=color, width=width)
    draw.line(
        [(cx - radius * 0.12, y0 + radius * 0.06), (cx + radius * 0.12, y0 + radius * 0.06)],
        fill=color, width=width,
    )
    return img


def extract_ring_layer(source: Image.Image, cx: float, cy: float, r_inner: float, r_outer: float) -> Image.Image:
    """Recorta del original solo la banda circular (anillo) entre r_inner
    y r_outer; el resto queda transparente. Esta zona no se solapa con el
    texto central, así que el recorte sale limpio."""
    w, h = source.size
    mask = Image.new("L", (w, h), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.ellipse([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer], fill=255)
    mdraw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner], fill=0)
    ring = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ring.paste(source.convert("RGBA"), (0, 0), mask)
    return ring


def build_static_layer(source: Image.Image, cx: float, cy: float, r_outer: float, protect_box) -> Image.Image:
    """El original con el círculo completo (anillo + patrón interior)
    hecho transparente, salvo `protect_box` (donde vive el texto
    central) — así se ve a través el patrón redibujado y el anillo
    recortado, que van por debajo."""
    w, h = source.size
    keep_mask = Image.new("L", (w, h), 255)
    kdraw = ImageDraw.Draw(keep_mask)
    kdraw.ellipse([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer], fill=0)
    x0, y0, x1, y1 = protect_box
    kdraw.rectangle([x0, y0, x1, y1], fill=255)

    static = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    static.paste(source.convert("RGBA"), (0, 0), keep_mask)
    return static


def _sample_bg_color(source: Image.Image) -> tuple:
    """Color de fondo real tomado de la esquina superior izquierda (igual
    que thumbnail_template.py) — evita una costura visible si el negro
    "de verdad" de la imagen no es (0,0,0) exacto."""
    w, h = source.size
    corner = source.convert("RGB").crop((0, 0, min(30, w), min(30, h)))
    pixels = list(corner.getdata())
    return tuple(sum(c) // len(pixels) for c in zip(*pixels))


def _rotate_layer(layer: Image.Image, cx: float, cy: float, angle_deg: float) -> Image.Image:
    # PIL rota alrededor del centro de la imagen entera, no de (cx, cy);
    # como cx/cy pueden no ser el centro exacto del lienzo, se rota
    # siempre el lienzo completo (el resto es transparente) para que el
    # giro quede centrado en el punto correcto sin desplazar nada.
    return layer.rotate(angle_deg, resample=Image.BICUBIC, center=(cx, cy))


def render_frame(
    source: Image.Image,
    static_layer: Image.Image,
    ring_layer: Image.Image,
    inner_pattern: Image.Image,
    cx: float, cy: float,
    ring_angle_deg: float, inner_angle_deg: float,
    bg_color=(0, 0, 0),
) -> Image.Image:
    w, h = source.size
    frame = Image.new("RGBA", (w, h), bg_color + (255,))
    frame.alpha_composite(_rotate_layer(inner_pattern, cx, cy, inner_angle_deg))
    frame.alpha_composite(_rotate_layer(ring_layer, cx, cy, ring_angle_deg))
    frame.alpha_composite(static_layer)
    return frame.convert("RGB")


def render_rotating_background(
    source_image_path: str,
    out_video_path: str,
    geometry: EmblemGeometry = None,
    duration: float = 40.0,
    fps: int = 25,
    ring_rpm: float = 2.0,       # vueltas por minuto del anillo exterior (antihorario)
    inner_rpm: float = 3.0,      # vueltas por minuto del patrón interior (horario)
) -> str:
    """Genera un vídeo (loop de `duration` segundos) con el anillo
    exterior girando antihorario e patrón interior redibujado girando
    horario, todo lo demás fijo. Usa ffmpeg para codificar los
    fotogramas ya renderizados con PIL."""
    geo = geometry or EmblemGeometry()
    source = Image.open(source_image_path).convert("RGBA")
    size = source.size[0]  # se asume imagen cuadrada, como la portada del LP
    cx, cy, r_outer, r_inner_ring, r_inner_pattern, protect_box = _abs_geometry(geo, size)
    bg_color = _sample_bg_color(source)

    ring_layer = extract_ring_layer(source, cx, cy, r_inner_ring, r_outer)
    static_layer = build_static_layer(source, cx, cy, r_outer, protect_box)
    inner_pattern = draw_inner_pattern(size, cx, cy, r_inner_pattern, geo)

    n_frames = int(duration * fps)
    ring_deg_per_frame = -(ring_rpm * 360.0 / 60.0) / fps    # negativo = antihorario
    inner_deg_per_frame = (inner_rpm * 360.0 / 60.0) / fps   # positivo = horario

    tmp_dir = Path(tempfile.mkdtemp(prefix="rotating_emblem_"))
    try:
        for i in range(n_frames):
            frame = render_frame(
                source, static_layer, ring_layer, inner_pattern,
                cx, cy,
                ring_angle_deg=ring_deg_per_frame * i,
                inner_angle_deg=inner_deg_per_frame * i,
                bg_color=bg_color,
            )
            frame.save(tmp_dir / f"frame_{i:05d}.png")

        cmd = [
            "ffmpeg", "-y", "-framerate", str(fps),
            "-i", str(tmp_dir / "frame_%05d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            out_video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg no pudo codificar el vídeo:\n{result.stderr[-2000:]}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return out_video_path


def preview_frame(source_image_path: str, out_image_path: str, geometry: EmblemGeometry = None, angle_deg: float = 40.0) -> str:
    """Genera UN fotograma de comprobación (con el anillo/patrón ya
    girados `angle_deg`) para ajustar la geometría rápido, sin renderizar
    el vídeo entero cada vez."""
    geo = geometry or EmblemGeometry()
    source = Image.open(source_image_path).convert("RGBA")
    size = source.size[0]
    cx, cy, r_outer, r_inner_ring, r_inner_pattern, protect_box = _abs_geometry(geo, size)

    ring_layer = extract_ring_layer(source, cx, cy, r_inner_ring, r_outer)
    static_layer = build_static_layer(source, cx, cy, r_outer, protect_box)
    inner_pattern = draw_inner_pattern(size, cx, cy, r_inner_pattern, geo)

    frame = render_frame(
        source, static_layer, ring_layer, inner_pattern,
        cx, cy, ring_angle_deg=-angle_deg, inner_angle_deg=angle_deg,
        bg_color=_sample_bg_color(source),
    )
    frame.save(out_image_path)
    return out_image_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Uso: python -m src.rotating_emblem <imagen_origen> <salida.mp4|salida.png> [--preview]")
        sys.exit(1)

    src_path, out_path = sys.argv[1], sys.argv[2]
    if "--preview" in sys.argv:
        preview_frame(src_path, out_path)
        print(f"Fotograma de prueba: {out_path}")
    else:
        render_rotating_background(src_path, out_path)
        print(f"Vídeo generado: {out_path}")
