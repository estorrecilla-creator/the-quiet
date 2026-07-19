"""
video_generator.py
Genera el vídeo largo (para YouTube normal) a partir de:
  - un audio (mp3/wav)
  - una o varias imágenes de portada (jpg/png). Con varias, cada una recibe
    su propio movimiento de cámara (zoom/paneo) y se encadenan en el tiempo.

Todo con ffmpeg puro, sin depender de moviepy (mucho más rápido y estable
para renders largos de audio+imagen).
"""

import os
import subprocess
import tempfile
from pathlib import Path

import soundfile as sf

from src.ffmpeg_utils import escape_path
from src.star_light import build_star_script, STAR_SIZE
from src.lyrics import srt_to_ass, subtitles_filter_fragment
from src.person_mask import extract_person_cutout, blank_rgba_like
from src.cover_sequence import build_cover_sequence_filter, compute_beat_synced_segment_durations, build_video_clip_chain, MOVEMENTS
from src.watermark import make_watermark_sticker, watermark_overlay_filter
from src.cinematic_grade import cinematic_grade_filter

STAR_FPS = 12
GLOW_ASSET = str(Path(__file__).resolve().parent.parent / "assets" / "glow.png")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".m4v")


def _get_audio_duration(audio_path: str) -> float:
    info = sf.info(audio_path)
    return info.frames / info.samplerate


def _is_video_file(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def _extract_reference_frame(video_path: str, t: float = 1.0) -> str:
    """
    Saca un fotograma del clip para usarlo donde hace falta una imagen
    fija (el contorno de la estrella, la detección de personas) — un
    clip de vídeo no sirve directamente para eso.

    Por defecto se coge en t=1.0s, NO el fotograma 0: algunos clips (ej.
    los montados con fundido a negro al empezar, ver src/film_editor.py)
    tienen el primer fotograma en negro puro — con eso de referencia, el
    detector de personas puede confundir el negro con "una persona
    ocupando todo el encuadre" y generar un recorte negro que tapa el
    vídeo entero (fallo real detectado y reproducido: vídeo con audio
    pero completamente negro).
    """
    out_path = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(t), "-i", video_path, "-frames:v", "1", "-q:v", "2", out_path],
        capture_output=True,
    )
    return out_path


def generate_main_video(
    audio_path: str,
    cover_path,
    output_path: str,
    resolution: str = "1920x1080",
    zoom_speed: float = 0.0002,
    zoom_max: float = 1.15,
    lyrics_path: str = None,
    lyrics_offset: float = 0.0,
    track_title: str = None,
    watermark_logo_path: str = None,
    watermark_opacity: float = 0.65,
):
    """
    Genera un vídeo horizontal (YouTube). `cover_path` puede ser una sola
    ruta de imagen, o una lista de rutas: con varias, el vídeo se reparte a
    partes iguales entre ellas, cada una con su propio movimiento de cámara
    (zoom in/out, paneo), en vez de una portada fija.

    Encima va un pequeño punto de luz que recorre despacio los contornos
    reales de la primera portada, variando su intensidad con la energía del
    audio (es la única parte que "reacciona" al ritmo) — pasa por detrás de
    la persona detectada en cada imagen (si la hay) y por delante del resto.
    Si se pasa `lyrics_path` (.srt con los tiempos de la letra), se
    superpone sincronizada.
    """
    w, h = map(int, resolution.split("x"))

    covers = list(cover_path) if isinstance(cover_path, (list, tuple)) else [cover_path]
    covers_are_video = [_is_video_file(c) for c in covers]
    # Un clip de vídeo no sirve directamente donde hace falta una imagen fija
    # (contorno de la estrella, detección de personas) — se saca un
    # fotograma de referencia para esos casos.
    reference_images = [
        _extract_reference_frame(c) if is_video else c
        for c, is_video in zip(covers, covers_are_video)
    ]
    temp_reference_images = [
        r for r, is_video in zip(reference_images, covers_are_video) if is_video
    ]

    star_script = build_star_script(audio_path, reference_images[0], w, h, fps=STAR_FPS)
    ass_path = None
    person_cutouts = None
    wm_sticker_path = None
    try:
        star_path_arg = escape_path(star_script)

        input_args = ["-i", audio_path]
        idx = 1

        if len(covers) == 1:
            if covers_are_video[0]:
                total_duration = _get_audio_duration(audio_path)
                chain = build_video_clip_chain(w, h, total_duration, fps=25)
                input_args += ["-stream_loop", "-1", "-t", f"{total_duration:.3f}", "-i", covers[0]]
            else:
                chain = (
                    f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                    f"scale=3840:2160,zoompan=z='min(zoom+{zoom_speed},{zoom_max})':d=1:s={w}x{h}:fps=25,setsar=1"
                )
                input_args += ["-loop", "1", "-i", covers[0]]
            cover_filter = f"[{idx}:v]{chain}[cover]"
            idx += 1
        else:
            total_duration = _get_audio_duration(audio_path)
            durations = compute_beat_synced_segment_durations(audio_path, total_duration, len(covers))
            for img, dur, is_video in zip(covers, durations, covers_are_video):
                if is_video:
                    input_args += ["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", img]
                else:
                    input_args += ["-loop", "1", "-t", f"{dur:.3f}", "-i", img]
            segment_types = ["video" if is_video else MOVEMENTS[i % len(MOVEMENTS)] for i, is_video in enumerate(covers_are_video)]
            cover_filter = build_cover_sequence_filter(
                len(covers), durations, w, h, 25, input_offset=idx, out_label="cover",
                segment_types=segment_types,
            )
            idx += len(covers)

        glow_idx = idx
        input_args += ["-loop", "1", "-i", GLOW_ASSET]
        idx += 1

        filter_complex = (
            f"{cover_filter};"
            f"[cover]sendcmd=f='{star_path_arg}'[coverstim];"
            f"[{glow_idx}:v]scale={STAR_SIZE}:{STAR_SIZE},format=rgba,sendcmd=f='{star_path_arg}',"
            f"colorchannelmixer=aa=0.5[star];"
            f"[coverstim][star]overlay=x=0:y=0[coverstar]"
        )

        # el recorte de persona congela UN fotograma y lo superpone
        # estático sobre la portada — con una imagen fija no se nota,
        # pero sobre un clip de vídeo real (portada = película) queda
        # una silueta fija encima de una imagen que sí se mueve por
        # debajo (efecto "ventana"/capa negra pegada, fallo real
        # reportado). Por eso solo se aplica con portada de imagen.
        raw_cutouts = [
            extract_person_cutout(img) if not is_video else None
            for img, is_video in zip(reference_images, covers_are_video)
        ]
        base_label = "coverstar"
        if any(c is not None for c in raw_cutouts):
            person_cutouts = [
                c if c else blank_rgba_like(img)
                for c, img in zip(raw_cutouts, reference_images)
            ]

            person_idx = idx
            for cutout in person_cutouts:
                if len(covers) == 1:
                    input_args += ["-loop", "1", "-i", cutout]
                else:
                    input_args += ["-loop", "1", "-t", f"{durations[0]:.3f}", "-i", cutout]
            idx += len(person_cutouts)

            if len(covers) == 1:
                person_zoom_chain = (
                    f"format=rgba,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                    f"scale=3840:2160,zoompan=z='min(zoom+{zoom_speed},{zoom_max})':d=1:s={w}x{h}:fps=25,setsar=1"
                )
                person_filter = f"[{person_idx}:v]{person_zoom_chain}[personcutout]"
            else:
                # capa de persona: corte simple (sin desvanecimiento) para no
                # arriesgar artefactos de transparencia con xfade
                person_filter = build_cover_sequence_filter(
                    len(person_cutouts), durations, w, h, 25,
                    input_offset=person_idx, out_label="personcutout",
                    use_transition=False,
                )

            filter_complex += (
                f";{person_filter};"
                f"[coverstar][personcutout]overlay=x=0:y=0[coverstarperson]"
            )
            base_label = "coverstarperson"
        else:
            for c in raw_cutouts:
                if c:
                    os.remove(c)

        # acabado cinematográfico (viñeta + grano + tinte sutil) sobre la
        # capa de fondo, antes de la letra/marca de agua (para no ensuciar
        # la legibilidad del texto ni oscurecer sus esquinas con la viñeta)
        filter_complex += f";{cinematic_grade_filter(base_label, 'graded')}"
        base_label = "graded"
        final_label = base_label

        if lyrics_path:
            margin_v = int(h * 0.04)
            ass_path = srt_to_ass(lyrics_path, w, h, margin_v, manual_shift=lyrics_offset)
            filter_complex += f";[{final_label}]{subtitles_filter_fragment(ass_path)}[outv1]"
            final_label = "outv1"

        if track_title or watermark_logo_path:
            wm_sticker_path = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
            make_watermark_sticker(
                wm_sticker_path, track_title=track_title, logo_path=watermark_logo_path,
                opacity=watermark_opacity,
            )
            input_args += ["-loop", "1", "-i", wm_sticker_path]
            filter_complex += f";{watermark_overlay_filter(final_label, 'outv', idx, w)}"
            idx += 1
            final_label = "outv"

        cmd = ["ffmpeg", "-y"] + input_args + [
            "-filter_complex", filter_complex,
            "-map", f"[{final_label}]", "-map", "0:a",
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
        if ass_path:
            os.remove(ass_path)
        if person_cutouts:
            for c in person_cutouts:
                os.remove(c)
        for r in temp_reference_images:
            os.remove(r)
        if wm_sticker_path:
            os.remove(wm_sticker_path)


if __name__ == "__main__":
    import sys

    audio, cover, out = sys.argv[1], sys.argv[2], sys.argv[3]
    generate_main_video(audio, cover, out)
    print(f"Generado: {out}")
