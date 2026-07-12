"""
pulse.py
Genera un script de comandos para el filtro `sendcmd` de ffmpeg que modula
brillo y saturación en función de la energía real del audio (RMS), para que
el vídeo "respire" con la música en vez de quedarse estático.
"""

import tempfile

from src.audio_analysis import energy_envelope
from src.ffmpeg_utils import escape_path as ffmpeg_filter_path  # noqa: F401  (re-exported for callers)


def build_pulse_script(
    audio_path: str,
    fps: float,
    offset: float = 0.0,
    duration: float = None,
    brightness_amp: float = 0.06,
    saturation_amp: float = 0.18,
):
    envelope = energy_envelope(audio_path, fps=fps, offset=offset, duration=duration)

    lines = []
    for i, e in enumerate(envelope):
        t = i / fps
        brightness = round((e - 0.5) * brightness_amp, 4)
        saturation = round(1.0 + (e - 0.5) * saturation_amp, 4)
        lines.append(f"{t:.3f} eq brightness {brightness};")
        lines.append(f"{t:.3f} eq saturation {saturation};")

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="pulse_", delete=False, encoding="utf-8"
    )
    tmp.write("\n".join(lines))
    tmp.close()
    return tmp.name
