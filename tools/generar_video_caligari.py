"""
generar_video_caligari.py — genera el largometraje reinterpretado de
"El gabinete del Dr. Caligari": sustituye los rótulos originales por
otros nuevos (bilingüe, se elige idioma), recorta cada plano real a un
máximo de segundos (conservando el arranque de cada uno, que es donde
ocurre lo importante), y le pone de banda sonora el álbum completo de
The Hollow Hour, en orden, sin interludios (la duración ya encaja casi
exacta con el recorte por defecto -- ver tools/duracion_sin_textos.py).

Requiere haber analizado ya la película con
tools/duracion_sin_textos.py al menos una vez (usa la misma caché de
planos, no la vuelve a analizar).

Los 32 bloques de guion (tools/caligari_guion.json) se reparten entre
los planos de solo texto detectados, en orden, sin perder ninguno --
si hay menos planos de texto que bloques de guion (caso real: 23 planos
para 32 bloques), varios bloques consecutivos comparten el mismo plano
(mismo cartel, texto más largo).

Uso:
    python tools/generar_video_caligari.py "ruta\\pelicula.mp4" "ruta\\salida.mp4" --lang en
    python tools/generar_video_caligari.py "ruta\\pelicula.mp4" "ruta\\salida_es.mp4" --lang es --cap-real 27
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.film_editor import detect_scenes, tag_scene_types

GUION_PATH = REPO_ROOT / "tools" / "caligari_guion.json"
FONT_PATH = REPO_ROOT / "assets" / "fonts" / "Jura-Medium.ttf"

CARD_SIZE = (1920, 1080)
CARD_BG_COLOR = (19, 19, 19)
CARD_TEXT_COLOR = (222, 222, 222)
CARD_MARGIN = 260
CARD_MIN_SECONDS = 3.5
CARD_READING_CHARS_PER_SECOND = 15  # velocidad de lectura conservadora

DEFAULT_CAP_REAL_SECONDS = 27.0


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


def _wrap_text(text: str, font, draw, max_width: int):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _render_title_card(text: str, out_path: str, duration: float, font_size: int = 54):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", CARD_SIZE, CARD_BG_COLOR)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(FONT_PATH), font_size)
    max_width = CARD_SIZE[0] - 2 * CARD_MARGIN

    lines = _wrap_text(text, font, draw, max_width)
    line_height = int(font_size * 1.4)
    total_height = line_height * len(lines)
    y = (CARD_SIZE[1] - total_height) // 2

    for line in lines:
        w = draw.textlength(line, font=font)
        x = (CARD_SIZE[0] - w) // 2
        draw.text((x, y), line, font=font, fill=CARD_TEXT_COLOR)
        y += line_height

    frame_path = out_path + ".png"
    img.save(frame_path)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", frame_path,
            "-t", f"{duration:.3f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-vf", f"scale={CARD_SIZE[0]}:{CARD_SIZE[1]}",
            out_path,
        ],
        capture_output=True, text=True, check=True,
    )
    Path(frame_path).unlink()


def _card_duration(text: str) -> float:
    return max(CARD_MIN_SECONDS, len(text) / CARD_READING_CHARS_PER_SECOND)


def _extract_real_clip(film_path: str, start: float, end: float, cap_real: float, out_path: str):
    duration = min(end - start, cap_real)
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", film_path,
            "-t", f"{duration:.3f}",
            "-vf", f"scale={CARD_SIZE[0]}:{CARD_SIZE[1]}:force_original_aspect_ratio=decrease,"
                   f"pad={CARD_SIZE[0]}:{CARD_SIZE[1]}:(ow-iw)/2:(oh-ih)/2",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            out_path,
        ],
        capture_output=True, text=True, check=True,
    )


def _probe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def build_timeline(film_path: str, lang: str, cap_real: float, work_dir: Path):
    """
    Devuelve la lista de rutas de los clips ya renderizados, en orden,
    listos para concatenar -- planos reales recortados y carteles de
    texto nuevos en el idioma pedido, intercalados en el mismo orden en
    que aparecen en la película original.
    """
    print("-> Leyendo planos (caché de tools/duracion_sin_textos.py)...")
    scenes = detect_scenes(film_path)
    tagged = tag_scene_types(film_path, scenes)

    guion = json.loads(GUION_PATH.read_text(encoding="utf-8"))
    n_text_scenes = sum(1 for s in tagged if s.get("static"))
    if n_text_scenes == 0:
        raise RuntimeError("No se ha detectado ningún plano de texto -- revisa la caché de planos.")
    beat_groups = _distribute_items(guion, n_text_scenes)

    clip_paths = []
    text_slot = 0
    for i, scene in enumerate(tagged):
        if scene.get("static"):
            beats = beat_groups[text_slot]
            text_slot += 1
            text = "\n\n".join(b[lang] for b in beats)
            duration = _card_duration(text)
            out_path = str(work_dir / f"clip_{i:04d}_card.mp4")
            print(f"   [{i+1}/{len(tagged)}] cartel ({duration:.1f}s): {text[:60]}...")
            _render_title_card(text, out_path, duration)
        else:
            out_path = str(work_dir / f"clip_{i:04d}_real.mp4")
            _extract_real_clip(film_path, scene["start"], scene["end"], cap_real, out_path)
        clip_paths.append(out_path)

    if text_slot != n_text_scenes:
        raise AssertionError(f"Se han usado {text_slot} carteles pero había {n_text_scenes} planos de texto.")

    return clip_paths


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
    mudo, que es justo lo que pasaba antes de este arreglo).
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
        clip_paths = build_timeline(args.film_path, args.lang, args.cap_real, work_dir)

        print(f"-> Concatenando {len(clip_paths)} clips...")
        video_only_path = str(work_dir / "video_sin_audio.mp4")
        concat_clips(clip_paths, video_only_path, work_dir)

        print("-> Montando la banda sonora (álbum completo, en orden)...")
        album_audio_path = str(work_dir / "album.m4a")
        n_tracks = build_album_audio(args.audio_dir, album_audio_path, work_dir)
        print(f"   {n_tracks} temas concatenados.")

        print("-> Uniendo vídeo y banda sonora...")
        mux_video_audio(video_only_path, album_audio_path, args.out_path, work_dir)

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
