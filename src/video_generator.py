"""
video_generator.py
Genera el vídeo largo (para YouTube normal) a partir de:
  - un audio (mp3/wav)
  - una imagen de portada (jpg/png)

Usa el filtro nativo de ffmpeg `showwaves`/`avectorscope` mezclado sobre la
portada, sin depender de moviepy para esta parte (ffmpeg puro es mucho más
rápido y estable para renders largos de audio+imagen).

Estilo: portada de fondo + barra de forma de onda semitransparente en la
franja inferior (look estándar de canal de música/lyric-less video).
"""

import subprocess
import shlex
import os


def generate_main_video(
    audio_path: str,
    cover_path: str,
    output_path: str,
    resolution: str = "1920x1080",
    waveform_color: str = "0xE0B0FF",
    waveform_height_ratio: float = 0.22,
):
    """
    Genera un vídeo horizontal (YouTube) con portada fija + waveform animado
    en la franja inferior.
    """
    w, h = map(int, resolution.split("x"))
    wave_h = int(h * waveform_height_ratio)

    filter_complex = (
        f"[0:a]showwaves=s={w}x{wave_h}:mode=cline:colors={waveform_color}:rate=25,"
        f"format=rgba,colorchannelmixer=aa=0.85[wave];"
        f"[1:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h}[cover];"
        f"[cover][wave]overlay=0:{h - wave_h}:shortest=1[outv]"
    )

    cmd = (
        f'ffmpeg -y -i {shlex.quote(audio_path)} -loop 1 -i {shlex.quote(cover_path)} '
        f'-filter_complex "{filter_complex}" '
        f'-map "[outv]" -map 0:a '
        f'-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p '
        f'-c:a aac -b:a 192k -shortest {shlex.quote(output_path)}'
    )

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error:\n{result.stderr[-2000:]}")
    return output_path


if __name__ == "__main__":
    import sys

    audio, cover, out = sys.argv[1], sys.argv[2], sys.argv[3]
    generate_main_video(audio, cover, out)
    print(f"Generado: {out}")
