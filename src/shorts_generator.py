"""
shorts_generator.py
A partir de un momento (start, end) detectado por audio_analysis.py, recorta
el audio y genera un Short vertical 1080x1920 con portada + waveform,
más un fade in/out para que no empiece/acabe en seco.
"""

import os
import subprocess
from pathlib import Path

from src.ffmpeg_utils import escape_path
from src.star_light import build_star_script, STAR_SIZE

STAR_FPS = 12
GLOW_ASSET = str(Path(__file__).resolve().parent.parent / "assets" / "glow.png")


def generate_short(
    audio_path: str,
    cover_path: str,
    output_path: str,
    start: float,
    end: float,
    fade_duration: float = 0.6,
    waveform_color: str = "0xE0B0FF",
    waveform_rate: float = 7,
    zoom_speed: float = 0.0002,
    zoom_max: float = 1.15,
):
    duration = end - start
    w, h = 1080, 1920
    wave_h = int(h * 0.09)

    star_script = build_star_script(
        audio_path, cover_path, w, h, fps=STAR_FPS, offset=start, duration=duration
    )
    try:
        star_path_arg = escape_path(star_script)

        filter_complex = (
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade_duration},afade=t=out:st={duration - fade_duration}:d={fade_duration}[a0];"
            f"[a0]asplit=2[aout][avis];"
            f"[avis]showwaves=s={w}x{wave_h}:mode=cline:colors={waveform_color}:rate={waveform_rate},"
            f"format=rgba,colorchannelmixer=aa=0.5[wave];"
            f"[1:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"scale=2160:3840,zoompan=z='min(zoom+{zoom_speed},{zoom_max})':d=1:s={w}x{h}:fps=25,"
            f"setsar=1,sendcmd=f='{star_path_arg}'[cover];"
            f"[2:v]scale={STAR_SIZE}:{STAR_SIZE},format=rgba,sendcmd=f='{star_path_arg}',"
            f"colorchannelmixer=aa=0.5[star];"
            f"[cover][star]overlay=x=0:y=0[coverstar];"
            f"[coverstar][wave]overlay=0:(H-h)/2:shortest=1[outv]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-loop", "1", "-i", cover_path,
            "-loop", "1", "-i", GLOW_ASSET,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "[aout]", "-t", str(duration),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
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

    audio, cover, out, start, end = sys.argv[1:6]
    generate_short(audio, cover, out, float(start), float(end))
    print(f"Generado: {out}")
