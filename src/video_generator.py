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
from pathlib import Path

from src.ffmpeg_utils import escape_path
from src.star_light import build_star_script, STAR_SIZE
from src.lyrics import subtitles_filter_fragment

STAR_FPS = 12
GLOW_ASSET = str(Path(__file__).resolve().parent.parent / "assets" / "glow.png")


def generate_main_video(
    audio_path: str,
    cover_path: str,
    output_path: str,
    resolution: str = "1920x1080",
    waveform_color: str = "0xE0B0FF",
    waveform_height_ratio: float = 0.10,
    waveform_rate: float = 7,
    zoom_speed: float = 0.0002,
    zoom_max: float = 1.15,
    lyrics_path: str = None,
):
    """
    Genera un vídeo horizontal (YouTube) con portada + zoom lento (Ken Burns)
    + un pequeño punto de luz que recorre despacio los contornos reales de
    la portada, variando su intensidad con la energía del audio (es la
    única parte que "reacciona" al ritmo) + waveform fina, discreta y lenta
    (para un resultado relajante, no nervioso). Si se pasa `lyrics_path`
    (.srt con los tiempos de la letra), se superpone sincronizada.
    """
    w, h = map(int, resolution.split("x"))
    wave_h = int(h * waveform_height_ratio)

    star_script = build_star_script(audio_path, cover_path, w, h, fps=STAR_FPS)
    try:
        star_path_arg = escape_path(star_script)
        glow_path_arg = escape_path(GLOW_ASSET)

        filter_complex = (
            f"[0:a]showwaves=s={w}x{wave_h}:mode=cline:colors={waveform_color}:rate={waveform_rate},"
            f"format=rgba,colorchannelmixer=aa=0.5[wave];"
            f"[1:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"scale=3840:2160,zoompan=z='min(zoom+{zoom_speed},{zoom_max})':d=1:s={w}x{h}:fps=25,"
            f"setsar=1,sendcmd=f='{star_path_arg}'[cover];"
            f"[2:v]scale={STAR_SIZE}:{STAR_SIZE},format=rgba,sendcmd=f='{star_path_arg}',"
            f"colorchannelmixer=aa=0.5[star];"
            f"[cover][star]overlay=x=0:y=0[coverstar];"
            f"[coverstar][wave]overlay=0:{h - wave_h}:shortest=1[outv0]"
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
            "-loop", "1", "-i", GLOW_ASSET,
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
        os.remove(star_script)


if __name__ == "__main__":
    import sys

    audio, cover, out = sys.argv[1], sys.argv[2], sys.argv[3]
    generate_main_video(audio, cover, out)
    print(f"Generado: {out}")
