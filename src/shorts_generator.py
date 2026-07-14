"""
shorts_generator.py
A partir de un momento (start, end) detectado por audio_analysis.py, recorta
el audio y genera un Short vertical 1080x1920 con portada + waveform,
más un fade in/out para que no empiece/acabe en seco.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from src.ffmpeg_utils import escape_path
from src.star_light import build_star_script, STAR_SIZE
from src.lyrics import srt_to_ass, subtitles_filter_fragment
from src.person_mask import extract_person_cutout
from src.cover_sequence import build_movement_chain, build_video_clip_chain, MOVEMENTS

STAR_FPS = 12
GLOW_ASSET = str(Path(__file__).resolve().parent.parent / "assets" / "glow.png")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".m4v")


def _is_video_file(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def _extract_reference_frame(video_path: str) -> str:
    out_path = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-frames:v", "1", "-q:v", "2", out_path],
        capture_output=True,
    )
    return out_path


def generate_short(
    audio_path: str,
    cover_path: str,
    output_path: str,
    start: float,
    end: float,
    fade_duration: float = 0.6,
    waveform_color: str = "0xE0B0FF",
    waveform_rate: float = 7,
    movement: str = "zoom_in",
    lyrics_path: str = None,
    lyrics_offset: float = 0.0,
):
    duration = end - start
    w, h = 1080, 1920
    wave_h = int(h * 0.09)

    is_video = _is_video_file(cover_path)
    reference_image = _extract_reference_frame(cover_path) if is_video else cover_path

    star_script = build_star_script(
        audio_path, reference_image, w, h, fps=STAR_FPS, offset=start, duration=duration
    )
    ass_path = None
    person_cutout = extract_person_cutout(reference_image)
    try:
        star_path_arg = escape_path(star_script)

        cover_chain = (
            build_video_clip_chain(w, h, duration, fps=25) if is_video
            else build_movement_chain(movement, w, h, duration, fps=25)
        )
        # la capa de la persona (siempre una imagen fija) mantiene su propio
        # movimiento aunque la portada sea un clip de vídeo real
        person_chain = build_movement_chain(movement, w, h, duration, fps=25)

        filter_complex = (
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={fade_duration},afade=t=out:st={duration - fade_duration}:d={fade_duration}[a0];"
            f"[a0]asplit=2[aout][avis];"
            f"[avis]showwaves=s={w}x{wave_h}:mode=cline:colors={waveform_color}:rate={waveform_rate},"
            f"format=rgba,colorchannelmixer=aa=0.5[wave];"
            f"[1:v]{cover_chain},sendcmd=f='{star_path_arg}'[cover];"
            f"[2:v]scale={STAR_SIZE}:{STAR_SIZE},format=rgba,sendcmd=f='{star_path_arg}',"
            f"colorchannelmixer=aa=0.5[star];"
            f"[cover][star]overlay=x=0:y=0[coverstar]"
        )

        base_label = "coverstar"
        if person_cutout:
            filter_complex += (
                f";[3:v]format=rgba,{person_chain}[personcutout];"
                f"[coverstar][personcutout]overlay=x=0:y=0[coverstarperson]"
            )
            base_label = "coverstarperson"

        filter_complex += f";[{base_label}][wave]overlay=0:(H-h)/2:shortest=1[outv0]"

        if lyrics_path:
            margin_v = wave_h + 12
            ass_path = srt_to_ass(
                lyrics_path, w, h, margin_v, offset=start, duration=duration,
                manual_shift=lyrics_offset,
            )
            filter_complex += f";[outv0]{subtitles_filter_fragment(ass_path)}[outv]"
        else:
            filter_complex = filter_complex.replace("[outv0]", "[outv]")

        cmd = ["ffmpeg", "-y", "-i", audio_path]
        if is_video:
            cmd += ["-stream_loop", "-1", "-i", cover_path]
        else:
            cmd += ["-loop", "1", "-i", cover_path]
        cmd += ["-loop", "1", "-i", GLOW_ASSET]
        if person_cutout:
            cmd += ["-loop", "1", "-i", person_cutout]
        cmd += [
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
        if ass_path:
            os.remove(ass_path)
        if person_cutout:
            os.remove(person_cutout)
        if is_video:
            os.remove(reference_image)


if __name__ == "__main__":
    import sys

    audio, cover, out, start, end = sys.argv[1:6]
    generate_short(audio, cover, out, float(start), float(end))
    print(f"Generado: {out}")
