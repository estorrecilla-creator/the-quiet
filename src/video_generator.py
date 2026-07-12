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

import os
import subprocess

from src.pulse import build_pulse_script, ffmpeg_filter_path
from src.lyrics import subtitles_filter_fragment

PULSE_FPS = 12


def generate_main_video(
    audio_path: str,
    cover_path: str,
    output_path: str,
    resolution: str = "1920x1080",
    waveform_color: str = "0xE0B0FF",
    waveform_height_ratio: float = 0.10,
    zoom_speed: float = 0.0002,
    zoom_max: float = 1.15,
    lyrics_path: str = None,
):
    """
    Genera un vídeo horizontal (YouTube) con portada + zoom lento (Ken Burns)
    + un pulso de brillo/saturación sincronizado con la energía real del
    audio (la portada "respira" con la música) + waveform fina y discreta.
    Si se pasa `lyrics_path` (un .srt con los tiempos de la letra), se
    superpone sincronizada sobre el vídeo.
    """
    w, h = map(int, resolution.split("x"))
    wave_h = int(h * waveform_height_ratio)

    pulse_script = build_pulse_script(audio_path, fps=PULSE_FPS)
    try:
        pulse_path = ffmpeg_filter_path(pulse_script)

        filter_complex = (
            f"[0:a]showwaves=s={w}x{wave_h}:mode=cline:colors={waveform_color}:rate=25,"
            f"format=rgba,colorchannelmixer=aa=0.5[wave];"
            f"[1:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"scale=3840:2160,zoompan=z='min(zoom+{zoom_speed},{zoom_max})':d=1:s={w}x{h}:fps=25,"
            f"setsar=1,"
            f"sendcmd=f='{pulse_path}',"
            f"eq=brightness=0:saturation=1[cover];"
            f"[cover][wave]overlay=0:{h - wave_h}:shortest=1[outv0]"
        )

        if lyrics_path:
            margin_v = wave_h + 40
            filter_complex += (
                f";[outv0]{subtitles_filter_fragment(lyrics_path, margin_v)}[outv]"
            )
        else:
            filter_complex = filter_complex.replace("[outv0]", "[outv]")

        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-loop", "1", "-i", cover_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest",
            output_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg error:\n{result.stderr[-2000:]}")
        return output_path
    finally:
        os.remove(pulse_script)


if __name__ == "__main__":
    import sys

    audio, cover, out = sys.argv[1], sys.argv[2], sys.argv[3]
    generate_main_video(audio, cover, out)
    print(f"Generado: {out}")
