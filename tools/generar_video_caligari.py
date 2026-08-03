"""
generar_video_caligari.py — genera el largometraje reinterpretado de
"El gabinete del Dr. Caligari": quita los planos que solo son rótulos de
texto originales (usa la detección de src/film_editor.py, ver AVISO más
abajo sobre la caché), recorta cada plano real a un máximo de segundos
(conservando el arranque de cada uno, que es donde ocurre lo importante),
superpone el texto narrativo nuevo (bilingüe, se elige idioma) como
subtítulos sobre el propio metraje -- el vídeo NUNCA se congela ni corta
a una pantalla aparte, sigue reproduciéndose siempre -- y le pone de
banda sonora el álbum completo de The Hollow Hour, en orden, sin
interludios.

AVISO sobre la caché: si ya habías analizado esta película con una
versión anterior del detector de movimiento (antes de que se corrigiera
para ser robusto al grano de la cinta escaneada), borra el archivo
"<pelicula>.scenetypes.v2.json" junto a la película para que se vuelva a
analizar con el detector corregido -- si no, seguirá usando la
clasificación vieja, que dejaba pasar muchos rótulos de texto como si
fueran imagen real.

Los 32 bloques de guion (tools/caligari_guion.json) se reparten entre los
planos de solo texto detectados, en orden, sin perder ninguno -- cada
bloque se trocea a su vez en frases cortas tipo subtítulo (no aparece
todo el bloque de golpe), que se van mostrando en el punto de la
película donde estaba el rótulo original que sustituyen, superpuestas
sobre el metraje que esté reproduciéndose en ese momento (puede
extenderse sobre más de un plano si el texto tarda en leerse).

Uso:
    python tools/generar_video_caligari.py "ruta\\pelicula.mp4" "ruta\\salida.mp4" --lang en
    python tools/generar_video_caligari.py "ruta\\pelicula.mp4" "ruta\\salida_es.mp4" --lang es --cap-real 27
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.film_editor import detect_scenes, tag_scene_types

GUION_PATH = REPO_ROOT / "tools" / "caligari_guion.json"
FONTS_DIR = REPO_ROOT / "assets" / "fonts"
FONT_NAME = "Jura Medium"

FRAME_SIZE = (1920, 1080)
DEFAULT_CAP_REAL_SECONDS = 27.0

MAX_PHRASE_CHARS = 70
MIN_PHRASE_SECONDS = 1.8
READING_CHARS_PER_SECOND = 16

_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡"])')
_CLAUSE_SPLIT_RE = re.compile(r',\s+|\s+—\s*|\s+--\s*')


def _distribute_items(items, n_buckets):
    """
    Reparte `items` (en orden) entre `n_buckets` grupos, lo más
    equilibrado posible, sin perder ninguno -- si hay más items que
    buckets, varios items consecutivos comparten el mismo bucket. Truco
    estándar (i*n_buckets//n) para repartir N elementos en K grupos
    conservando el orden y la proporción.
    """
    n = len(items)
    buckets = [[] for _ in range(n_buckets)]
    for i, item in enumerate(items):
        idx = i * n_buckets // n
        buckets[idx].append(item)
    return buckets


def _split_into_phrases(text: str, max_chars: int = MAX_PHRASE_CHARS):
    """
    Trocea un bloque de guion en frases cortas tipo subtítulo: primero
    por frase (puntos/interrogaciones/exclamaciones), y si alguna frase
    sigue siendo muy larga, además por comas/guiones -- para que nunca
    aparezca un bloque entero de golpe en pantalla.
    """
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    phrases = []
    for sentence in sentences:
        if len(sentence) <= max_chars:
            phrases.append(sentence)
            continue
        parts = [p.strip() for p in _CLAUSE_SPLIT_RE.split(sentence) if p.strip()]
        buf = ""
        for part in parts:
            candidate = f"{buf}, {part}" if buf else part
            if len(candidate) <= max_chars:
                buf = candidate
            else:
                if buf:
                    phrases.append(buf)
                buf = part
        if buf:
            phrases.append(buf)
    return phrases


def _phrase_duration(phrase: str) -> float:
    return max(MIN_PHRASE_SECONDS, len(phrase) / READING_CHARS_PER_SECOND)


def _extract_real_clip(film_path: str, start: float, end: float, cap_real: float, out_path: str):
    duration = min(end - start, cap_real)
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", film_path,
            "-t", f"{duration:.3f}",
            "-vf", f"scale={FRAME_SIZE[0]}:{FRAME_SIZE[1]}:force_original_aspect_ratio=decrease,"
                   f"pad={FRAME_SIZE[0]}:{FRAME_SIZE[1]}:(ow-iw)/2:(oh-ih)/2",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            out_path,
        ],
        capture_output=True, text=True, check=True,
    )
    return duration


def _probe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def build_timeline(film_path: str, lang: str, cap_real: float, work_dir: Path):
    """
    Devuelve (real_clip_paths, caption_events): la lista de planos reales
    ya recortados y listos para concatenar (el vídeo, sin ningún corte a
    cartel aparte -- los planos de solo texto se OMITEN del vídeo, no se
    sustituyen por nada visual propio), y la lista de subtítulos a
    superponer (start, end, texto) en segundos dentro del vídeo final
    resultante, en el punto exacto donde estaba cada rótulo original.
    """
    print("-> Leyendo planos (usa la caché si ya existe; borra el .scenetypes.v2.json si la analizaste con una versión vieja del detector)...")
    scenes = detect_scenes(film_path)
    tagged = tag_scene_types(film_path, scenes)

    guion = json.loads(GUION_PATH.read_text(encoding="utf-8"))
    n_text_scenes = sum(1 for s in tagged if s.get("static"))
    if n_text_scenes == 0:
        raise RuntimeError("No se ha detectado ningún plano de texto -- revisa la caché de planos.")
    beat_groups = _distribute_items(guion, n_text_scenes)

    real_clip_paths = []
    caption_events = []
    cumulative_time = 0.0
    text_slot = 0

    for i, scene in enumerate(tagged):
        if scene.get("static"):
            beats = beat_groups[text_slot]
            text_slot += 1
            phrases = []
            for beat in beats:
                phrases.extend(_split_into_phrases(beat[lang]))
            t = cumulative_time
            for phrase in phrases:
                dur = _phrase_duration(phrase)
                caption_events.append((t, t + dur, phrase))
                t += dur
        else:
            out_path = str(work_dir / f"clip_{i:04d}_real.mp4")
            dur = _extract_real_clip(film_path, scene["start"], scene["end"], cap_real, out_path)
            real_clip_paths.append(out_path)
            cumulative_time += dur

    if text_slot != n_text_scenes:
        raise AssertionError(f"Se han usado {text_slot} bloques pero había {n_text_scenes} planos de texto.")
    if not real_clip_paths:
        raise RuntimeError("No queda ningún plano real tras quitar los de texto -- revisa la detección de planos.")

    return real_clip_paths, caption_events


def concat_clips(clip_paths, out_path: str, work_dir: Path):
    list_path = work_dir / "concat_list.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in clip_paths:
            escaped = p.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
         "-c", "copy", out_path],
        capture_output=True, text=True, check=True,
    )


def _format_srt_timestamp(seconds: float) -> str:
    ms_total = int(round(seconds * 1000))
    h, ms_total = divmod(ms_total, 3600000)
    m, ms_total = divmod(ms_total, 60000)
    s, ms = divmod(ms_total, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(caption_events, out_path: str):
    lines = []
    for i, (start, end, text) in enumerate(caption_events, start=1):
        lines.append(str(i))
        lines.append(f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}")
        lines.append(text)
        lines.append("")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


def _escape_for_ffmpeg_filter(path: str) -> str:
    """
    Los filtros de ffmpeg usan ':' como separador de opciones -- una ruta
    de Windows tipo "C:\\..." rompe el filtro si no se escapa. Se
    escapan las barras invertidas y los dos puntos, y se envuelve todo
    entre comillas simples (sintaxis que entiende libavfilter).
    """
    escaped = path.replace("\\", "/").replace(":", "\\:")
    return escaped


def burn_subtitles(video_path: str, srt_path: str, out_path: str):
    srt_arg = _escape_for_ffmpeg_filter(str(srt_path))
    fonts_arg = _escape_for_ffmpeg_filter(str(FONTS_DIR))
    style = (
        f"FontName={FONT_NAME},FontSize=26,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=3,BackColour=&H90000000,"
        "Alignment=2,MarginV=60"
    )
    vf = f"subtitles='{srt_arg}':fontsdir='{fonts_arg}':force_style='{style}'"
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vf", vf,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", out_path],
        capture_output=True, text=True, check=True,
    )


def build_album_audio(audio_dir: str, out_path: str, work_dir: Path):
    """Concatena, en orden por nombre de archivo, todos los .wav de
    `audio_dir` (el álbum completo) en una sola pista continua."""
    tracks = sorted(Path(audio_dir).glob("*.wav"))
    if not tracks:
        raise RuntimeError(f"No encuentro ningún .wav en {audio_dir}")
    list_path = work_dir / "audio_concat_list.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for t in tracks:
            escaped = str(t).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
         "-c:a", "aac", "-b:a", "256k", out_path],
        capture_output=True, text=True, check=True,
    )
    return len(tracks)


def mux_video_audio(video_path: str, audio_path: str, out_path: str, work_dir: Path):
    """
    Une vídeo y audio, ajustando la duración del más corto para que
    coincidan exactos: si el vídeo es más corto que el álbum, se
    mantiene congelado el último fotograma el tiempo que falte (para no
    cortar el final del álbum); si el vídeo es más largo que el álbum,
    se rellena el audio con silencio (para no dejar el resto del vídeo
    mudo).
    """
    video_duration = _probe_duration(video_path)
    audio_duration = _probe_duration(audio_path)
    diff = audio_duration - video_duration  # positivo => el álbum dura más que el vídeo

    final_video_path = video_path
    final_audio_path = audio_path

    if diff > 0.05:
        print(f"   El vídeo es {diff:.1f}s más corto que el álbum -- se sostiene el último fotograma ese tiempo.")
        padded_path = str(work_dir / "video_padded.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_path,
             "-vf", f"tpad=stop_mode=clone:stop_duration={diff:.3f}",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", padded_path],
            capture_output=True, text=True, check=True,
        )
        final_video_path = padded_path
    elif diff < -0.05:
        pad_seconds = -diff
        print(f"   El álbum es {pad_seconds:.1f}s más corto que el vídeo -- se rellena con silencio ese tiempo.")
        padded_audio_path = str(work_dir / "audio_padded.m4a")
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path,
             "-af", f"apad=pad_dur={pad_seconds:.3f}",
             "-c:a", "aac", "-b:a", "256k", padded_audio_path],
            capture_output=True, text=True, check=True,
        )
        final_audio_path = padded_audio_path

    subprocess.run(
        ["ffmpeg", "-y", "-i", final_video_path, "-i", final_audio_path,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
         "-shortest", out_path],
        capture_output=True, text=True, check=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("film_path")
    parser.add_argument("out_path")
    parser.add_argument("--lang", choices=["en", "es"], default="en")
    parser.add_argument("--cap-real", type=float, default=DEFAULT_CAP_REAL_SECONDS)
    parser.add_argument("--audio-dir", default=str(REPO_ROOT / "MUSICA" / "IWT" / "The Hollow Hour" / "AUDIO_FINAL"))
    parser.add_argument("--keep-work-dir", action="store_true", help="No borrar los clips intermedios al terminar (para depurar)")
    args = parser.parse_args()

    if not Path(args.film_path).exists():
        print(f"No encuentro la película: {args.film_path}")
        sys.exit(1)

    work_dir = Path(tempfile.mkdtemp(prefix="caligari_"))
    print(f"-> Directorio de trabajo: {work_dir}")

    try:
        real_clip_paths, caption_events = build_timeline(args.film_path, args.lang, args.cap_real, work_dir)
        print(f"   {len(real_clip_paths)} planos reales conservados, {len(caption_events)} subtítulos a superponer.")

        print(f"-> Concatenando {len(real_clip_paths)} planos reales (sin cortes a cartel aparte)...")
        video_only_path = str(work_dir / "video_sin_subtitulos.mp4")
        concat_clips(real_clip_paths, video_only_path, work_dir)

        print("-> Generando y quemando los subtítulos nuevos sobre el vídeo...")
        srt_path = str(work_dir / "captions.srt")
        build_srt(caption_events, srt_path)
        video_with_subs_path = str(work_dir / "video_con_subtitulos.mp4")
        burn_subtitles(video_only_path, srt_path, video_with_subs_path)

        print("-> Montando la banda sonora (álbum completo, en orden)...")
        album_audio_path = str(work_dir / "album.m4a")
        n_tracks = build_album_audio(args.audio_dir, album_audio_path, work_dir)
        print(f"   {n_tracks} temas concatenados.")

        print("-> Uniendo vídeo y banda sonora...")
        mux_video_audio(video_with_subs_path, album_audio_path, args.out_path, work_dir)

        final_duration = _probe_duration(args.out_path)
        h, rem = divmod(int(final_duration), 3600)
        m, s = divmod(rem, 60)
        print(f"\n-> Listo: {args.out_path} ({h}h {m}min {s}s)" if h else f"\n-> Listo: {args.out_path} ({m}min {s}s)")
    finally:
        if not args.keep_work_dir:
            import shutil
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            print(f"-> Clips intermedios conservados en: {work_dir}")


if __name__ == "__main__":
    main()
