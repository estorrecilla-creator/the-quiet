"""
loudness.py
Normaliza el volumen final del audio al estándar de sonoridad que usan
YouTube y las plataformas de streaming: -14 LUFS integrados, con un
límite de pico real de -1 dBTP para no recortar. Sin esto, un tema más
flojo o más fuerte que el resto de tu catálogo suena descompensado al
pasar de un vídeo a otro del mismo canal — YouTube normaliza en
reproducción, pero solo hacia abajo si te pasas de fuerte; un tema flojo
se queda flojo.

Usa el filtro `loudnorm` de ffmpeg en dos pasadas (medir + aplicar) para
un resultado preciso, sin tocar la ecualización ni la dinámica más allá
de lo necesario para llegar al nivel objetivo. Se aplica después de
cualquier masterización con Matchering (que ajusta tono/color a una
referencia, pero no garantiza un LUFS exacto).
"""

import json
import re
import subprocess
from pathlib import Path

import soundfile as sf

TARGET_I = -14.0   # LUFS integrados (estándar YouTube/Spotify)
TARGET_TP = -1.0   # dBTP, margen de pico real para evitar clipping
TARGET_LRA = 11.0  # rango de sonoridad objetivo


def measure_loudness(audio_path: str) -> dict:
    """
    Primera pasada: mide la sonoridad real del audio sin tocarlo. Devuelve
    None si no se puede parsear la medición (para que el que llama pueda
    caer en una normalización de una sola pasada, menos precisa pero
    igualmente válida).
    """
    result = subprocess.run(
        [
            "ffmpeg", "-i", audio_path,
            "-af", f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    start = result.stderr.rfind("{")
    end = result.stderr.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(result.stderr[start:end + 1])
    except json.JSONDecodeError:
        return None


def normalize_loudness(audio_path: str, out_path: str) -> str:
    """
    Normaliza `audio_path` al nivel objetivo y lo guarda en `out_path`
    (creando la carpeta si hace falta), conservando el sample rate
    original. Dos pasadas si la medición sale bien (más precisa),
    una sola pasada como respaldo si no.
    """
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    sample_rate = sf.info(audio_path).samplerate

    measured = measure_loudness(audio_path)
    if measured:
        loudnorm_filter = (
            f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:"
            f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
            f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
            f"offset={measured['target_offset']}:linear=true:print_format=summary"
        )
    else:
        loudnorm_filter = f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=summary"

    subprocess.run(
        ["ffmpeg", "-y", "-i", audio_path, "-af", loudnorm_filter, "-ar", str(sample_rate), out_path],
        capture_output=True,
    )
    return out_path


if __name__ == "__main__":
    import sys

    src, out = sys.argv[1], sys.argv[2]
    normalize_loudness(src, out)
    print(f"Generado: {out}")
