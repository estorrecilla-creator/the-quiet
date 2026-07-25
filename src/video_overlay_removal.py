"""
video_overlay_removal.py
Detecta y quita gráficos/texto "quemados" en el propio vídeo (fecha,
telemetría, marca de agua de la misión/NASA...) ANTES de montarlo con
`film_editor.py` -- muy habitual en vídeo real de archivo (Apolo, sondas,
ISS, animaciones JPL...), donde ese tipo de overlay suele quedarse fijo en
la misma zona de la imagen (típicamente arriba/abajo/una esquina) mientras
el resto del encuadre cambia (la nave se mueve, la cámara panea, el
planeta gira, las estrellas se desplazan).

Método (heurístico, no siempre perfecto -- ver aviso en `detect_overlay_
regions`): se muestrean varios fotogramas repartidos por todo el vídeo y,
solo dentro de las franjas típicas de overlay (bordes/esquinas, nunca el
centro del encuadre), se buscan zonas que a la vez:
1. apenas cambian de un fotograma a otro (un overlay fijo no se mueve,
   aunque el fondo sí), y
2. tienen mucho detalle/contraste local (el texto tiene muchos trazos
   finos, a diferencia de un cielo o una superficie lisa).
Esas dos condiciones juntas son releventes: una nube o un planeta
inmóviles varios fotogramas seguidos NO tienen apenas trazos finos, así
que no se confunden con texto.

Las zonas detectadas se rellenan con el filtro `delogo` de ffmpeg
(interpola desde los píxeles de alrededor, no deja un hueco negro).
"""

import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

from src.film_editor import _probe_duration

# overlays de misión suelen ir en bordes/esquinas -- nunca se toca el
# centro del encuadre, aunque coincidiera con las dos condiciones, para no
# arriesgarse a borrar imagen real por error.
_BAND_TOP = 0.20
_BAND_BOTTOM = 0.24
_BAND_SIDE = 0.14


def _extract_sample_frames(video_path: str, n_samples: int = 12, downscale_width: int = 480):
    duration = _probe_duration(video_path)
    # se evita el primer/último 5% -- ahí es donde suelen ir cortinillas/
    # cartelas de crédito que no son overlay fijo del vídeo en sí.
    margin = duration * 0.05
    times = np.linspace(margin, duration - margin, n_samples)

    frames = []
    orig_size = None
    with tempfile.TemporaryDirectory(prefix="overlay_frames_") as tmp:
        for i, t in enumerate(times):
            out = str(Path(tmp) / f"f{i:03d}.jpg")
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(t), "-i", video_path, "-frames:v", "1", out],
                capture_output=True,
            )
            if not Path(out).exists():
                continue
            img = cv2.imread(out, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            if orig_size is None:
                orig_size = (img.shape[1], img.shape[0])  # (w, h)
            scale = downscale_width / img.shape[1]
            small = cv2.resize(img, (downscale_width, max(1, int(img.shape[0] * scale))))
            frames.append(small.astype(np.float32))
    return frames, orig_size


def detect_overlay_regions(
    video_path: str, n_samples: int = 12, still_std_thresh: float = 5.0,
    edge_thresh: float = 18.0, min_area_frac: float = 0.0008,
):
    """
    Devuelve una lista de rectángulos [{"x","y","w","h"}, ...] EN LA
    RESOLUCIÓN ORIGINAL del vídeo, candidatos a overlay fijo (texto/logo
    quemado). Lista vacía si no se detecta ninguno -- es lo normal en
    vídeo de la NASA "limpio", sin telemetría superpuesta.

    Aviso: es un heurístico, no un OCR ni una detección de logos entrenada
    -- puede no detectar overlays sutiles (muy tenues) o, más raramente,
    marcar como overlay un detalle real que por casualidad quedara quieto
    y con mucho contraste en el borde del encuadre durante toda la
    muestra. Por eso se limita a las franjas de borde/esquina (nunca el
    centro) y exige AMBAS condiciones (quieto Y con mucho detalle), no
    solo una.
    """
    frames, orig_size = _extract_sample_frames(video_path, n_samples=n_samples)
    if len(frames) < 3 or orig_size is None:
        return []

    stack = np.stack(frames, axis=0)
    temporal_std = stack.std(axis=0)

    edge_mags = [cv2.Laplacian(f.astype(np.uint8), cv2.CV_32F) for f in frames]
    edge_avg = np.mean([np.abs(e) for e in edge_mags], axis=0)

    h, w = temporal_std.shape
    border_mask = np.zeros((h, w), dtype=bool)
    top = int(h * _BAND_TOP)
    bottom = int(h * (1 - _BAND_BOTTOM))
    side = int(w * _BAND_SIDE)
    border_mask[:top, :] = True
    border_mask[bottom:, :] = True
    border_mask[:, :side] = True
    border_mask[:, w - side:] = True

    candidate = (temporal_std < still_std_thresh) & (edge_avg > edge_thresh) & border_mask
    candidate_u8 = candidate.astype(np.uint8)

    # cierre morfológico: une trazos de texto cercanos en un único bloque
    # rectangular en vez de decenas de blobs diminutos (una letra cada uno).
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 5))
    closed = cv2.morphologyEx(candidate_u8, cv2.MORPH_CLOSE, kernel, iterations=2)

    num_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(closed, connectivity=8)
    min_area = min_area_frac * h * w

    orig_w, orig_h = orig_size
    scale_x = orig_w / w
    scale_y = orig_h / h
    pad = 4  # margen extra en píxeles (a resolución reducida) para no dejar un borde sin tapar
    # `delogo` interpola desde los píxeles justo FUERA del rectángulo, así
    # que necesita que quede sitio alrededor -- si la caja tocara el borde
    # real del fotograma, ffmpeg la rechaza ("Logo area is outside of the
    # frame"). Se deja un margen mínimo de seguridad a resolución original.
    edge_margin = 6

    boxes = []
    for i in range(1, num_labels):  # 0 es el fondo
        x, y, bw, bh, area = stats[i]
        if area < min_area:
            continue
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(w, x + bw + pad)
        y1 = min(h, y + bh + pad)

        bx = max(edge_margin, int(x0 * scale_x))
        by = max(edge_margin, int(y0 * scale_y))
        bx1 = min(orig_w - edge_margin, int(x1 * scale_x))
        by1 = min(orig_h - edge_margin, int(y1 * scale_y))
        if bx1 - bx < 4 or by1 - by < 4:
            continue  # demasiado pequeño/pegado al borde tras el margen -- se descarta
        boxes.append({"x": bx, "y": by, "w": bx1 - bx, "h": by1 - by})
    return boxes


def remove_overlays(video_path: str, out_path: str, boxes=None) -> bool:
    """
    Aplica `delogo` a cada rectángulo de `boxes` (o los detecta él mismo
    si no se pasan) y escribe el resultado en `out_path`. Devuelve True si
    se ha aplicado algún tratamiento (out_path es un vídeo nuevo), False
    si no se detectó ningún overlay (no se escribe nada, el vídeo
    original ya vale tal cual -- evita un re-encode innecesario)."""
    if boxes is None:
        boxes = detect_overlay_regions(video_path)
    if not boxes:
        return False

    filter_chain = ",".join(
        f"delogo=x={b['x']}:y={b['y']}:w={b['w']}:h={b['h']}:show=0" for b in boxes
    )
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", filter_chain,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        "-c:a", "copy",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg no pudo aplicar delogo a {video_path}:\n{result.stderr[-1500:]}")
    return True


def clean_video_overlays(video_path: str, cache_suffix: str = ".clean.mp4") -> str:
    """
    Punto de entrada práctico: limpia `video_path` de overlays fijos si
    detecta alguno, cacheando el resultado junto al propio archivo (no se
    repite el análisis/tratamiento si ya se hizo antes). Devuelve la ruta
    a USAR de aquí en adelante (el archivo limpio si se trató algo, o el
    original tal cual si no se detectó ningún overlay)."""
    cache_path = str(Path(video_path).with_suffix("")) + cache_suffix
    if Path(cache_path).exists():
        return cache_path

    treated = remove_overlays(video_path, cache_path)
    return cache_path if treated else video_path
