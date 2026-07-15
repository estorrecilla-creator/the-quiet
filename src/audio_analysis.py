"""
audio_analysis.py
Analiza un archivo de audio y detecta los "mejores momentos" (climax, subidas
de energía, cambios de sección) para usarlos como candidatos a Shorts.

Estrategia:
1. Calculamos la envolvente de energía RMS por ventanas.
2. Detectamos "onsets" (ataques/transitorios) para saber dónde hay cambios
   estructurales (entra la batería, sube el coro, etc).
3. Buscamos ventanas de N segundos (por defecto 20-45s, configurable) con
   mayor energía sostenida Y que coincidan con un onset fuerte al inicio
   (para no cortar el clip a mitad de frase musical).
4. Aplicamos non-max suppression para no devolver 5 momentos casi seguidos.

Salida: lista de dicts [{"start": float, "end": float, "score": float}, ...]
ordenada por score descendente.
"""

import numpy as np
import librosa


def find_best_moments(
    audio_path: str,
    clip_duration: float = 30.0,
    top_n: int = 5,
    min_gap: float = 45.0,
    sr: int = 22050,
):
    y, sr = librosa.load(audio_path, sr=sr, mono=True)
    total_duration = librosa.get_duration(y=y, sr=sr)

    if total_duration <= clip_duration:
        return [{"start": 0.0, "end": total_duration, "score": 1.0}]

    hop_length = 512
    # 1. Energía RMS
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)

    # 2. Onsets (fuerza del transitorio en cada frame)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)

    # 3. Ventana deslizante: para cada posible inicio (cada 2s), calculamos
    #    energía media de la ventana + bonus si arranca cerca de un onset fuerte
    step = 2.0
    candidates = []
    onset_norm = onset_env / (onset_env.max() + 1e-9)
    rms_norm = rms / (rms.max() + 1e-9)

    t = 0.0
    while t + clip_duration <= total_duration:
        start_frame = int(t * sr / hop_length)
        end_frame = int((t + clip_duration) * sr / hop_length)
        end_frame = min(end_frame, len(rms_norm))

        if end_frame <= start_frame:
            t += step
            continue

        window_energy = float(np.mean(rms_norm[start_frame:end_frame]))
        # bonus si el arranque coincide con un pico de onset (entrada de sección)
        onset_bonus = float(np.max(onset_norm[start_frame:min(start_frame + 10, len(onset_norm))])) if start_frame < len(onset_norm) else 0.0

        score = window_energy * 0.7 + onset_bonus * 0.3
        candidates.append({"start": t, "end": t + clip_duration, "score": score})
        t += step

    # 4. Ordenar por score y aplicar non-max suppression (evitar solapes/cercanía)
    candidates.sort(key=lambda c: c["score"], reverse=True)
    selected = []
    for c in candidates:
        if all(abs(c["start"] - s["start"]) >= min_gap for s in selected):
            selected.append(c)
        if len(selected) >= top_n:
            break

    selected.sort(key=lambda c: c["start"])
    return selected


def find_many_moments(
    audio_path: str,
    n: int,
    clip_duration: float = 15.0,
    sr: int = 22050,
):
    """
    Como `find_best_moments`, pero pensada para pedir MUCHOS momentos a la
    vez (ej. 45, uno por cada Short cuando un tema tiene 15 clips de vídeo
    descargados y se generan 3 Shorts por clip). Si el tema no es lo
    bastante largo para tener `n` tramos de `clip_duration` segundos sin
    solaparse el `min_gap` de siempre, lo relaja automáticamente hasta
    conseguir tantos tramos distintos como se pueda; si aun así no llega a
    `n`, completa la lista repitiendo en orden los mejores momentos ya
    encontrados (mismo tramo de audio, combinado con un clip de vídeo
    distinto cada vez, en vez de fallar o dejar Shorts sin generar).
    """
    if n <= 0:
        return []

    min_gap = clip_duration
    moments = find_best_moments(audio_path, clip_duration=clip_duration, top_n=n, min_gap=min_gap, sr=sr)
    while len(moments) < n and min_gap > 1.0:
        min_gap = max(1.0, min_gap / 2)
        moments = find_best_moments(audio_path, clip_duration=clip_duration, top_n=n, min_gap=min_gap, sr=sr)

    if moments and len(moments) < n:
        moments = [moments[i % len(moments)] for i in range(n)]
    return moments


def energy_envelope(
    audio_path: str,
    fps: float = 12.0,
    sr: int = 22050,
    offset: float = 0.0,
    duration: float = None,
):
    """
    Devuelve la energía RMS normalizada (0..1) del audio, muestreada a `fps`
    puntos por segundo. Se usa para sincronizar efectos visuales (pulso de
    brillo/color) con la música real, en vez de una animación genérica.
    """
    y, sr = librosa.load(audio_path, sr=sr, mono=True, offset=offset, duration=duration)
    if len(y) == 0:
        return [0.0]

    hop_length = max(1, int(sr / fps))
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    peak = float(rms.max())
    if peak < 1e-9:
        return [0.0] * len(rms)
    return (rms / peak).tolist()


if __name__ == "__main__":
    import sys
    import json

    path = sys.argv[1]
    moments = find_best_moments(path)
    print(json.dumps(moments, indent=2))
