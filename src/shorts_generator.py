"""
shorts_generator.py
A partir de un momento (start, end) detectado por audio_analysis.py, recorta
el audio y genera un Short vertical 1080x1920 con portada, más un fade
in/out para que no empiece/acabe en seco.
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
from src.watermark import make_watermark_sticker, pick_logo_variant, watermark_overlay_filter
from src.cinematic_grade import cinematic_grade_filter

STAR_FPS = 12
GLOW_ASSET = str(Path(__file__).resolve().parent.parent / "assets" / "glow.png")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".m4v")


def _is_video_file(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def _format_srt_time(t: float) -> str:
    t = max(t, 0.0)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _build_hook_srt(text: str, duration: float) -> str:
    """
    .srt de una sola línea (el texto "gancho", ej. el título del tema)
    mostrada desde el segundo 0 — para los Shorts sin letra real
    (instrumentales): el 85% de los Shorts se ven sin sonido al
    principio, así que conviene que se lea algo desde el primer momento
    aunque no haya letra que sincronizar.
    """
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".srt", prefix="hook_", delete=False, encoding="utf-8",
    )
    tmp.write(f"1\n00:00:00,000 --> {_format_srt_time(duration)}\n{text}\n\n")
    tmp.close()
    return tmp.name


def _extract_reference_frame(video_path: str, t: float = 0.0) -> str:
    out_path = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(t), "-i", video_path, "-frames:v", "1", "-q:v", "2", out_path],
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
    movement: str = "zoom_in",
    lyrics_path: str = None,
    lyrics_offset: float = 0.0,
    track_title: str = None,
    watermark_logo_light_path: str = None,
    watermark_logo_dark_path: str = None,
    watermark_opacity: float = 0.65,
    cover_offset: float = 0.0,
    hook_text: str = None,
    hook_duration: float = 3.5,
):
    """
    `hook_text`: si no hay `lyrics_path` (Short instrumental, sin letra
    que sincronizar), muestra este texto (normalmente el título del
    tema) desde el segundo 0 durante `hook_duration` segundos — el 85%
    de los Shorts se ven sin sonido al principio, así que conviene que
    se lea algo desde ya aunque no haya letra. Se ignora si `lyrics_path`
    sí está presente (la letra real tiene prioridad).
    """
    duration = end - start
    w, h = 1080, 1920

    is_video = _is_video_file(cover_path)
    reference_image = _extract_reference_frame(cover_path, t=cover_offset) if is_video else cover_path

    star_script = build_star_script(
        audio_path, reference_image, w, h, fps=STAR_FPS, offset=start, duration=duration
    )
    ass_path = None
    wm_sticker_path = None
    hook_srt_path = None
    # el recorte de persona congela UN fotograma y lo superpone estático
    # sobre la portada — con una imagen fija no se nota, pero sobre un
    # clip de vídeo real (portada = película) queda una silueta fija
    # encima de una imagen que sí se mueve por debajo (efecto "ventana"/
    # capa negra pegada). Por eso solo se aplica con portada de imagen.
    person_cutout = extract_person_cutout(reference_image) if not is_video else None
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
            f"afade=t=in:st=0:d={fade_duration},afade=t=out:st={duration - fade_duration}:d={fade_duration}[aout];"
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

        # acabado cinematográfico (viñeta + grano + tinte sutil) sobre la
        # capa de fondo, antes de la letra/marca de agua
        filter_complex += f";{cinematic_grade_filter(base_label, 'graded')}"
        base_label = "graded"
        final_label = base_label

        if lyrics_path:
            margin_v = int(h * 0.04)
            ass_path = srt_to_ass(
                lyrics_path, w, h, margin_v, offset=start, duration=duration,
                manual_shift=lyrics_offset,
            )
            filter_complex += f";[{final_label}]{subtitles_filter_fragment(ass_path)}[outv1]"
            final_label = "outv1"
        elif hook_text:
            margin_v = int(h * 0.04)
            hook_srt_path = _build_hook_srt(hook_text, min(hook_duration, duration))
            # offset=0 (no `start`): el gancho está escrito ya en el tiempo
            # propio del Short (desde el segundo 0), no del tema completo.
            ass_path = srt_to_ass(hook_srt_path, w, h, margin_v, offset=0.0, duration=duration, karaoke=False)
            filter_complex += f";[{final_label}]{subtitles_filter_fragment(ass_path)}[outv1]"
            final_label = "outv1"

        cmd = ["ffmpeg", "-y", "-i", audio_path]
        if is_video:
            if cover_offset:
                cmd += ["-ss", str(cover_offset)]
            cmd += ["-stream_loop", "-1", "-i", cover_path]
        else:
            cmd += ["-loop", "1", "-i", cover_path]
        cmd += ["-loop", "1", "-i", GLOW_ASSET]
        next_idx = 3
        if person_cutout:
            cmd += ["-loop", "1", "-i", person_cutout]
            next_idx = 4

        if track_title or watermark_logo_light_path or watermark_logo_dark_path:
            chosen_logo_path = pick_logo_variant(
                cover_path, watermark_logo_light_path, watermark_logo_dark_path, is_video=is_video,
            )
            wm_sticker_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
            make_watermark_sticker(
                wm_sticker_path, track_title=track_title, logo_path=chosen_logo_path,
                opacity=watermark_opacity,
            )
            cmd += ["-loop", "1", "-i", wm_sticker_path]
            filter_complex += f";{watermark_overlay_filter(final_label, 'outv', next_idx, w)}"
            final_label = "outv"

        cmd += [
            "-filter_complex", filter_complex,
            "-map", f"[{final_label}]", "-map", "[aout]", "-t", str(duration),
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
        if hook_srt_path:
            os.remove(hook_srt_path)
        if person_cutout:
            os.remove(person_cutout)
        if is_video:
            os.remove(reference_image)
        if wm_sticker_path:
            os.remove(wm_sticker_path)


if __name__ == "__main__":
    import sys

    audio, cover, out, start, end = sys.argv[1:6]
    generate_short(audio, cover, out, float(start), float(end))
    print(f"Generado: {out}")
