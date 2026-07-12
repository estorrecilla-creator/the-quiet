"""
shorts_generator.py
A partir de un momento (start, end) detectado por audio_analysis.py, recorta
el audio y genera un Short vertical 1080x1920 con portada + waveform,
más un fade in/out para que no empiece/acabe en seco.
"""

import subprocess


def generate_short(
    audio_path: str,
    cover_path: str,
    output_path: str,
    start: float,
    end: float,
    fade_duration: float = 0.6,
    waveform_color: str = "0xE0B0FF",
    zoom_speed: float = 0.0002,
    zoom_max: float = 1.15,
):
    duration = end - start
    w, h = 1080, 1920
    wave_h = int(h * 0.09)

    filter_complex = (
        f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={fade_duration},afade=t=out:st={duration - fade_duration}:d={fade_duration}[a0];"
        f"[a0]asplit=2[aout][avis];"
        f"[avis]showwaves=s={w}x{wave_h}:mode=cline:colors={waveform_color}:rate=25,"
        f"format=rgba,colorchannelmixer=aa=0.5[wave];"
        f"[1:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"scale=2160:3840,zoompan=z='min(zoom+{zoom_speed},{zoom_max})':d=1:s={w}x{h}:fps=25,"
        f"setsar=1[cover];"
        f"[cover][wave]overlay=0:(H-h)/2:shortest=1[outv]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", audio_path,
        "-loop", "1", "-i", cover_path,
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


if __name__ == "__main__":
    import sys

    audio, cover, out, start, end = sys.argv[1:6]
    generate_short(audio, cover, out, float(start), float(end))
    print(f"Generado: {out}")
