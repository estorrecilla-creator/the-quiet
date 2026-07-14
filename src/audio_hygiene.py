"""
audio_hygiene.py
Limpieza básica del audio antes de generar el vídeo final: recorte de
silencio al principio/final (no toca los silencios internos, esos son
parte de la canción), aviso de compatibilidad mono (por si hay
cancelación de fase en la mezcla estéreo) y una reducción de ruido de
fondo muy conservadora, que solo se aplica si de verdad hay un suelo de
ruido audible (para no arriesgarse a "lavar" el brillo de una mezcla ya
terminada sin necesidad).
"""

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

NOISE_FLOOR_THRESHOLD_DB = -45.0  # por debajo de esto, se considera que hay ruido de fondo audible
DENOISE_STRENGTH_DB = 6.0         # reducción conservadora (el máximo de afftdn es 97dB)
MONO_CANCELLATION_THRESHOLD_DB = -3.0


def trim_silence(audio_path: str, out_path: str, threshold_db: float = -50.0) -> str:
    """
    Recorta el silencio del principio y del final (no el de en medio,
    forma parte de la canción). Truco estándar de ffmpeg: silenciar desde
    el principio, invertir, silenciar desde el principio otra vez (que
    ahora es el final), invertir de vuelta.
    """
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    filt = (
        f"silenceremove=start_periods=1:start_duration=0:start_threshold={threshold_db}dB:detection=peak,"
        "areverse,"
        f"silenceremove=start_periods=1:start_duration=0:start_threshold={threshold_db}dB:detection=peak,"
        "areverse"
    )
    subprocess.run(
        # pcm_s24le explícito: sin esto, ffmpeg vuelca el WAV de salida a
        # 16 bits por defecto aunque la entrada sea de 24 (o más), perdiendo
        # resolución del máster en cada paso de la cadena sin avisar.
        ["ffmpeg", "-y", "-i", audio_path, "-af", filt, "-c:a", "pcm_s24le", out_path],
        capture_output=True,
    )
    return out_path


def check_mono_compatibility(audio_path: str, threshold_db: float = MONO_CANCELLATION_THRESHOLD_DB) -> dict:
    """
    Suma el audio a mono (L+R)/2 y compara su energía con la media de los
    dos canales por separado. Una mezcla estéreo muy ancha (o con fase
    invertida en algún punto) pierde energía notable al sumarse a mono —
    eso se nota en dispositivos/plataformas que reproducen en mono. Solo
    es un diagnóstico: no modifica el audio.
    """
    data, sr = sf.read(audio_path)
    if data.ndim < 2 or data.shape[1] < 2:
        return {"is_stereo": False, "warning": False}

    left, right = data[:, 0], data[:, 1]
    mono = (left + right) / 2
    stereo_rms = float(np.sqrt(np.mean((left ** 2 + right ** 2) / 2)))
    mono_rms = float(np.sqrt(np.mean(mono ** 2)))

    if stereo_rms < 1e-9:
        return {"is_stereo": True, "warning": False, "diff_db": 0.0}

    diff_db = 20 * np.log10(max(mono_rms, 1e-12) / stereo_rms)
    return {"is_stereo": True, "diff_db": diff_db, "warning": diff_db < threshold_db}


def _estimate_noise_floor_db(audio_path: str, quiet_relative_db: float = -20.0):
    """
    Estima el suelo de ruido de fondo mirando SOLO las ventanas que son
    claramente más flojas que el pico de la pista (candidatas a "pasaje
    silencioso"), no un percentil ciego de toda la pista — una canción
    fuerte de principio a fin (sin pasajes flojos) no tiene forma fiable
    de distinguir señal de ruido, así que en ese caso se devuelve None
    (mejor no tocar nada que arriesgarse a adivinar mal).
    """
    data, sr = sf.read(audio_path)
    if data.ndim > 1:
        data = data.mean(axis=1)

    window = max(1, int(sr * 0.05))
    n_windows = len(data) // window
    if n_windows == 0:
        return None

    rms_values = np.array([
        np.sqrt(np.mean(data[i * window:(i + 1) * window] ** 2))
        for i in range(n_windows)
    ])
    peak_rms = rms_values.max()
    if peak_rms < 1e-9:
        return None

    peak_db = 20 * np.log10(peak_rms)
    window_db = 20 * np.log10(np.maximum(rms_values, 1e-12))
    quiet_values = rms_values[window_db < (peak_db + quiet_relative_db)]

    # hace falta un mínimo de pasajes flojos para que la estimación sea
    # representativa (no un par de ventanas sueltas por casualidad)
    if len(quiet_values) < max(3, n_windows * 0.02):
        return None

    floor = np.percentile(quiet_values, 50)
    return float(20 * np.log10(max(floor, 1e-12)))


def denoise_if_needed(audio_path: str, out_path: str) -> tuple:
    """
    Solo aplica una reducción de ruido muy conservadora (`afftdn`) si se
    puede estimar un suelo de ruido de fondo Y supera
    `NOISE_FLOOR_THRESHOLD_DB` — para no tocar una mezcla que ya está
    limpia, ni arriesgarse a adivinar en una pista sin pasajes flojos
    donde no hay forma fiable de medirlo. Devuelve (ruta_resultado,
    se_aplicó: bool, suelo_de_ruido_estimado_db_o_None).
    """
    noise_floor_db = _estimate_noise_floor_db(audio_path)
    if noise_floor_db is None or noise_floor_db < NOISE_FLOOR_THRESHOLD_DB:
        return audio_path, False, noise_floor_db

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", audio_path, "-af", f"afftdn=nr={DENOISE_STRENGTH_DB}", "-c:a", "pcm_s24le", out_path],
        capture_output=True,
    )
    return out_path, True, noise_floor_db
