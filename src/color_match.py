"""
color_match.py
Analiza el brillo medio de varios clips de vídeo (de fuentes distintas, por
lo que llegan con exposición/paleta distinta cada uno) y calcula una
corrección de brillo por clip para acercarlos todos a un mismo punto medio,
para que el salto de un clip a otro se note menos.
"""

import os
import subprocess
import tempfile

import numpy as np
from PIL import Image


def _get_video_duration(video_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def get_average_brightness(video_path: str, sample_frames: int = 3) -> float:
    """
    Brillo medio (0.0-1.0) de un clip, muestreando unos pocos fotogramas
    repartidos a lo largo de su duración (más fiable que mirar solo el
    primer fotograma).
    """
    duration = _get_video_duration(video_path)
    values = []
    for i in range(sample_frames):
        t = duration * (i + 0.5) / sample_frames
        frame_path = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", video_path, "-frames:v", "1", frame_path],
                capture_output=True,
            )
            img = np.array(Image.open(frame_path).convert("L"))
            values.append(img.mean() / 255.0)
        finally:
            if os.path.exists(frame_path):
                os.remove(frame_path)
    return sum(values) / len(values) if values else 0.5


def compute_brightness_correction(current_brightness: float, target_brightness: float, max_correction: float = 0.3) -> float:
    """
    Valor para el parámetro `brightness` del filtro `eq` de ffmpeg (rango
    típico -1.0 a 1.0) que acerca `current_brightness` a
    `target_brightness`, limitado para no generar artefactos visibles si
    el clip está muy sobre/subexpuesto.
    """
    delta = target_brightness - current_brightness
    return max(-max_correction, min(max_correction, delta))


def apply_color_correction(video_path: str, brightness: float = 0.0, saturation: float = 1.0, out_path: str = None) -> str:
    """
    Re-codifica el clip aplicando la corrección de brillo y una saturación
    fija (para una paleta más consistente entre clips), a `out_path` (o
    sobrescribiendo el original si no se indica).
    """
    out_path = out_path or video_path
    tmp_out = out_path + ".tmp.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"eq=brightness={brightness:.4f}:saturation={saturation:.4f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-an", tmp_out,
        ],
        capture_output=True,
    )
    os.replace(tmp_out, out_path)
    return out_path


def homogenize_clips(video_paths, saturation: float = 1.0, sample_frames: int = 3):
    """
    Analiza el brillo de cada clip de `video_paths`, calcula un punto medio
    común, y corrige cada uno hacia ese punto (in-place). Si solo hay un
    clip, no hace nada (no hay nada que homogeneizar).
    """
    if len(video_paths) < 2:
        return video_paths

    brightness_values = [get_average_brightness(p, sample_frames=sample_frames) for p in video_paths]
    target = sum(brightness_values) / len(brightness_values)

    for path, current in zip(video_paths, brightness_values):
        correction = compute_brightness_correction(current, target)
        apply_color_correction(path, brightness=correction, saturation=saturation)

    return video_paths
