"""
video_generator.py
Genera el vídeo largo (para YouTube normal) a partir de:
  - un audio (mp3/wav)
  - una o varias imágenes de portada (jpg/png). Con varias, cada una recibe
    su propio movimiento de cámara (zoom/paneo) y se encadenan en el tiempo.

Usa el filtro nativo de ffmpeg `showwaves`/`avectorscope` mezclado sobre la
portada, sin depender de moviepy para esta parte (ffmpeg puro es mucho más
rápido y estable para renders largos de audio+imagen).

Estilo: portada de fondo + barra de forma de onda semitransparente en la
franja inferior (look estándar de canal de música/lyric-less video).
"""

import os
import subprocess
from pathlib import Path

import soundfile as sf

from src.ffmpeg_utils import escape_path
from src.star_light import build_star_script, STAR_SIZE
from src.lyrics import srt_to_ass, subtitles_filter_fragment
from src.person_mask import extract_person_cutout, blank_rgba_like
from src.cover_sequence import build_cover_sequence_filter, compute_segment_durations

STAR_FPS = 12
GLOW_ASSET = str(Path(__file__).resolve().parent.parent / "assets" / "glow.png")


def _get_audio_duration(audio_path: str) -> float:
    info = sf.info(audio_path)
    return info.frames / info.samplerate


def generate_main_video(
    audio_path: str,
    cover_path,
    output_path: str,
    resolution: str = "1920x1080",
    waveform_color: str = "0xE0B0FF",
    waveform_height_ratio: float = 0.10,
    waveform_rate: float = 7,
    zoom_speed: float = 0.0002,
    zoom_max: float = 1.15,
    lyrics_path: str = None,
    lyrics_offset: float = 0.0,
):
    """
    Genera un vídeo horizontal (YouTube). `cover_path` puede ser una sola
    ruta de imagen, o una lista de rutas: con varias, el vídeo se reparte a
    partes iguales entre ellas, cada una con su propio movimiento de cámara
    (zoom in/out, paneo), en vez de una portada fija.

    Encima va un pequeño punto de luz que recorre despacio los contornos
    reales de la primera portada, variando su intensidad con la energía del
    audio (es la única parte que "reacciona" al ritmo) — pasa por detrás de
    la persona detectada en cada imagen (si la hay) y por delante del resto
    + waveform fina, discreta y lenta (para un resultado relajante). Si se
    pasa `lyrics_path` (.srt con los tiempos de la letra), se superpone
    sincronizada.
    """
    w, h = map(int, resolution.split("x"))
    wave_h = int(h * waveform_height_ratio)

    covers = list(cover_path) if isinstance(cover_path, (list, tuple)) else [cover_path]

    star_script = build_star_script(audio_path, covers[0], w, h, fps=STAR_FPS)
    ass_path = None
    person_cutouts = None
    try:
        star_path_arg = escape_path(star_script)

        input_args = ["-i", audio_path]
        idx = 1

        if len(covers) == 1:
            zoom_chain = (
                f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
                f"scale=3840:2160,zoompan=z='min(zoom+{zoom_speed},{zoom_max})':d=1:s={w}x{h}:fps=25,setsar=1"
            )
            input_args += ["-loop", "1", "-i", covers[0]]
            cover_filter = f"[{idx}:v]{zoom_chain}[cover]"
            idx += 1
        else:
            total_duration = _get_audio_duration(audio_path)
            durations = compute_segment_durations(total_duration, len(covers))
            for img, dur in zip(covers, durations):
                input_args += ["-loop", "1", "-t", f"{dur:.3f}", "-i", img]
            cover_filter = build_cover_sequence_filter(
                len(covers), durations, w, h, 25, input_offset=idx, out_label="cover"
            )
            idx += len(covers)

        glow_idx = idx
        input_args += ["-loop", "1", "-i", GLOW_ASSET]
        idx += 1

        filter_complex = (
            f"[0:a]showwaves=s={w}x{wave_h}:mode=cline:colors={waveform_color}:rate={waveform_rate},"
            f"format=rgba,colorchannelmixer=aa=0.5[wave];"
            f"{cover_filter};"
            f"[cover]sendcmd=f='{star_path_arg}'[coverstim];"
            f"[{glow_idx}:v]scale={STAR_SIZE}:{STAR_SIZE},format=rgba,sendcmd=f='{star_path_arg}',"
            f"colorchannelmixer=aa=0.5[star];"
            f"[coverstim][star]overlay=x=0:y=0[coverstar]"
        )

        raw_cutouts = [extract_person_cutout(img) for img in covers]
        base_label = "coverstar"
        if any(c is not None for c in raw_cutouts):
            person_cutouts = [c if c else blank_rgba_like(img) for c, img in zip(raw_cutouts, covers)]

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

        filter_complex += f";[{base_label}][wave]overlay=0:{h - wave_h}:shortest=1[outv0]"

        if lyrics_path:
            margin_v = wave_h + 12
            ass_path = srt_to_ass(lyrics_path, w, h, margin_v, manual_shift=lyrics_offset)
            filter_complex += (
                f";[outv0]{subtitles_filter_fragment(ass_path)}[outv]"
            )
        else:
            filter_complex = filter_complex.replace("[outv0]", "[outv]")

        cmd = ["ffmpeg", "-y"] + input_args + [
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
        if ass_path:
            os.remove(ass_path)
        if person_cutouts:
            for c in person_cutouts:
                os.remove(c)


if __name__ == "__main__":
    import sys

    audio, cover, out = sys.argv[1], sys.argv[2], sys.argv[3]
    generate_main_video(audio, cover, out)
    print(f"Generado: {out}")
