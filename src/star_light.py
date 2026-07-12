"""
star_light.py
Genera el script `sendcmd` que mueve un pequeño punto de luz a lo largo de
un contorno real de la portada (ver star_path.py), variando su intensidad
según la energía real del audio (ver audio_analysis.energy_envelope). Es la
única parte del vídeo que "reacciona" al ritmo; el resto queda quieto.
"""

import tempfile

from src.audio_analysis import energy_envelope
from src.star_path import extract_contour_path

STAR_SIZE = 64


def build_star_script(
    audio_path: str,
    cover_path: str,
    width: int,
    height: int,
    fps: float,
    loop_duration: float = 50.0,
    offset: float = 0.0,
    duration: float = None,
    min_alpha: float = 0.15,
    max_alpha: float = 0.9,
):
    path = extract_contour_path(cover_path)
    n = len(path)

    envelope = energy_envelope(audio_path, fps=fps, offset=offset, duration=duration)

    lines = []
    for i, e in enumerate(envelope):
        t = i / fps
        frac = (t % loop_duration) / loop_duration
        px, py = path[int(frac * n) % n]
        x = round(px * width - STAR_SIZE / 2, 1)
        y = round(py * height - STAR_SIZE / 2, 1)
        alpha = round(min_alpha + e * (max_alpha - min_alpha), 4)

        lines.append(f"{t:.3f} overlay x {x};")
        lines.append(f"{t:.3f} overlay y {y};")
        lines.append(f"{t:.3f} colorchannelmixer aa {alpha};")

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="star_", delete=False, encoding="utf-8"
    )
    tmp.write("\n".join(lines))
    tmp.close()
    return tmp.name
