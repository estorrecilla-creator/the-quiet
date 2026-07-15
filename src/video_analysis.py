"""
video_analysis.py
Detecta el instante de mayor movimiento dentro de un clip de vídeo (banco
de vídeo libre de derechos), para usarlo como punto de partida del "mejor
momento del vídeo" en los Shorts generados a partir de esos clips —
mismo espíritu que `audio_analysis.find_best_moments`, pero sobre imagen
en vez de sobre audio, porque hasta ahora los clips siempre se usaban
desde su segundo 0 sin mirar si ahí pasaba algo interesante o no.
"""

import subprocess

import numpy as np

SAMPLE_SIZE = (64, 36)  # bajísima resolución: solo hace falta estimar movimiento, no verlo


def _probe_duration(video_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def find_best_video_moment(video_path: str, duration: float, sample_fps: float = 6.0) -> float:
    """
    Devuelve el segundo de inicio (dentro del propio clip) de la ventana
    de `duration` segundos con más movimiento medio entre fotogramas
    consecutivos (diferencia de píxeles sobre una copia reducida a
    escala de grises, decodificada a `sample_fps`). Si el clip es más
    corto que `duration`, o algo falla al analizarlo, devuelve 0.0 (usar
    el clip desde el principio, el comportamiento de antes).
    """
    total = _probe_duration(video_path)
    if total <= duration:
        return 0.0

    w, h = SAMPLE_SIZE
    cmd = [
        "ffmpeg", "-i", video_path, "-vf", f"scale={w}:{h},format=gray",
        "-r", str(sample_fps), "-f", "rawvideo", "-",
    ]
    result = subprocess.run(cmd, capture_output=True)
    frame_size = w * h
    data = result.stdout
    n_frames = len(data) // frame_size
    if n_frames < 2:
        return 0.0

    frames = np.frombuffer(data[: n_frames * frame_size], dtype=np.uint8)
    frames = frames.reshape(n_frames, h, w).astype(np.float32)
    diffs = np.mean(np.abs(np.diff(frames, axis=0)), axis=(1, 2))

    win = max(1, int(round(duration * sample_fps)))
    if len(diffs) < win:
        return 0.0

    window_sums = np.convolve(diffs, np.ones(win), mode="valid")
    best_idx = int(np.argmax(window_sums))
    best_start = best_idx / sample_fps
    return max(0.0, min(best_start, total - duration))


if __name__ == "__main__":
    import sys

    video, dur = sys.argv[1], float(sys.argv[2])
    print(find_best_video_moment(video, dur))
