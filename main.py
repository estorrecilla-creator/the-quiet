"""
main.py — Orquestador del pipeline completo.

Uso:
    python main.py --audio input/cancion.mp3 --cover input/portada.jpg \
        --artist "Telvorn" --title "Caminante" --genre "doom-folk / post-rock" \
        --context "Tema sobre..." --shorts 3

Para un LP completo, pásale una carpeta con varias pistas:
    python main.py --album-dir input/mi_lp/ --cover input/portada.jpg \
        --artist "Telvorn" --genre "..." --context "..." --shorts 2
"""

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from src.audio_analysis import find_best_moments
from src.video_generator import generate_main_video
from src.shorts_generator import generate_short
from src.metadata_generator import generate_metadata
from src.lyrics_align import resolve_lyrics_srt
from src.cover_sequence import MOVEMENTS

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".m4v")
COVER_EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS


def resolve_cover(cover_arg):
    """
    Si `cover_arg` es una carpeta, devuelve la lista ordenada de imágenes
    y/o clips de vídeo que contiene (cada una tendrá su propio movimiento
    de cámara en el vídeo principal, o su movimiento real si ya es un
    clip). Si es un archivo, lo devuelve tal cual.
    """
    path = Path(cover_arg)
    if path.is_dir():
        images = sorted(
            p for p in path.iterdir() if p.suffix.lower() in COVER_EXTENSIONS
        )
        if not images:
            raise ValueError(f"La carpeta {cover_arg} no contiene imágenes ni vídeos (.jpg/.png/.mp4...).")
        return [str(p) for p in images]
    return cover_arg


def process_track(
    audio_path, cover_path, artist, title, genre, context, n_shorts, out_dir,
    lyrics_path=None, lyrics_offset=0.0, shorts_cover_override=None,
    watermark_logo_path=None,
):
    out_dir = Path(out_dir) / title.replace(" ", "_")
    out_dir.mkdir(parents=True, exist_ok=True)

    cover = resolve_cover(cover_path)
    if shorts_cover_override:
        # portada (imagen o clip) buscada/generada específicamente en
        # orientación vertical para los Shorts, en vez de reutilizar la del
        # vídeo principal (pensada en horizontal).
        cover_for_shorts = shorts_cover_override
    elif isinstance(cover, list):
        # sin una portada vertical dedicada: entre las del vídeo principal
        # (pensadas en horizontal), se prefiere una imagen fija a un clip de
        # vídeo para los Shorts, ya que no sabemos si el clip es horizontal
        # o vertical y recortarlo a lo bruto puede quedar peor que la imagen.
        images_only = [c for c in cover if Path(c).suffix.lower() in IMAGE_EXTENSIONS]
        cover_for_shorts = images_only[0] if images_only else cover[0]
    else:
        cover_for_shorts = cover

    print(f"\n=== Procesando: {title} ===")

    if lyrics_path and lyrics_path.lower().endswith(".txt"):
        print("-> Sincronizando la letra con el audio (puede tardar unos minutos)...")
    lyrics_srt, lyrics_is_temp = resolve_lyrics_srt(audio_path, lyrics_path)

    if lyrics_srt and lyrics_is_temp:
        # Guardamos el .srt auto-sincronizado en la carpeta de salida para
        # que se pueda revisar/corregir a mano y reutilizar directamente
        # como .srt (sin volver a pasar por el reconocimiento de voz).
        saved_srt = out_dir / "letra_sincronizada.srt"
        with open(lyrics_srt, encoding="utf-8") as f:
            saved_srt.write_text(f.read(), encoding="utf-8")
        print(f"-> Letra auto-sincronizada guardada en: {saved_srt}")
        print("   Si sale desfasada, ábrela y ajusta a mano los tiempos, o "
              "usa un offset manual.")

    try:
        # 1. Vídeo principal
        print("-> Generando vídeo principal...")
        main_video_path = out_dir / "main_video.mp4"
        generate_main_video(
            audio_path, cover, str(main_video_path), lyrics_path=lyrics_srt,
            lyrics_offset=lyrics_offset, track_title=title,
        )

        print("-> Generando metadatos del vídeo principal...")
        main_meta = generate_metadata(artist, title, genre, context, content_type="main")
        with open(out_dir / "main_video_metadata.json", "w", encoding="utf-8") as f:
            json.dump(main_meta, f, ensure_ascii=False, indent=2)

        # 2. Mejores momentos -> Shorts
        print(f"-> Detectando {n_shorts} mejores momentos...")
        moments = find_best_moments(audio_path, top_n=n_shorts)

        for i, moment in enumerate(moments, start=1):
            print(f"-> Generando Short {i} ({moment['start']:.1f}s - {moment['end']:.1f}s)...")
            short_path = out_dir / f"short_{i}.mp4"
            generate_short(
                audio_path, cover_for_shorts, str(short_path), moment["start"], moment["end"],
                movement=MOVEMENTS[(i - 1) % len(MOVEMENTS)],
                lyrics_path=lyrics_srt,
                lyrics_offset=lyrics_offset,
                track_title=title,
                watermark_logo_path=watermark_logo_path,
            )

            short_meta = generate_metadata(artist, title, genre, context, content_type="short")
            with open(out_dir / f"short_{i}_metadata.json", "w", encoding="utf-8") as f:
                json.dump(short_meta, f, ensure_ascii=False, indent=2)
    finally:
        if lyrics_is_temp:
            os.remove(lyrics_srt)

    print(f"=== Listo: {out_dir} ===")
    return out_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", help="Ruta a un único archivo de audio")
    parser.add_argument("--album-dir", help="Carpeta con varias pistas para procesar como LP")
    parser.add_argument(
        "--cover",
        required=True,
        help=(
            "Ruta a la imagen de portada, o a una carpeta con varias "
            "imágenes (cada una tendrá su propio movimiento de cámara "
            "en el vídeo principal)"
        ),
    )
    parser.add_argument("--artist", required=True)
    parser.add_argument("--title", help="Título del tema (obligatorio si usas --audio)")
    parser.add_argument("--genre", required=True)
    parser.add_argument("--context", required=True, help="Contexto/concepto artístico")
    parser.add_argument("--shorts", type=int, default=3, help="Número de shorts a generar por tema")
    parser.add_argument("--out", default="output", help="Carpeta de salida")
    parser.add_argument(
        "--lyrics",
        help=(
            "Letra para superponer en el vídeo principal: un .srt ya "
            "sincronizado, o un .txt en texto plano (una frase por línea) "
            "para sincronizarlo automáticamente contra el audio"
        ),
    )
    parser.add_argument(
        "--lyrics-offset",
        type=float,
        default=0.0,
        help=(
            "Ajuste manual en segundos de la letra (positivo = retrasa, "
            "negativo = adelanta). Útil si el reconocimiento automático "
            "la deja algo desfasada. Ej: -3 si sale 3s tarde."
        ),
    )
    parser.add_argument(
        "--watermark-logo",
        help=(
            "Ruta a un logo en PNG con fondo transparente, para quemarlo "
            "junto al nombre del tema en la esquina superior izquierda de "
            "los Shorts (el vídeo principal lleva solo el nombre del tema; "
            "el logo ahí lo pone el watermark de canal de YouTube, ver "
            "configurar_marca_agua.py). Opcional."
        ),
    )
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        parser.error(
            "Falta ANTHROPIC_API_KEY. Copia .env.example a .env y añade tu "
            "clave (ANTHROPIC_API_KEY=sk-ant-...) antes de ejecutar."
        )

    if args.audio:
        if not args.title:
            parser.error("--title es obligatorio cuando usas --audio")
        process_track(
            args.audio, args.cover, args.artist, args.title,
            args.genre, args.context, args.shorts, args.out,
            lyrics_path=args.lyrics, lyrics_offset=args.lyrics_offset,
            watermark_logo_path=args.watermark_logo,
        )
    elif args.album_dir:
        tracks = sorted(Path(args.album_dir).glob("*.mp3")) + sorted(Path(args.album_dir).glob("*.wav"))
        for track_path in tracks:
            track_title = track_path.stem
            process_track(
                str(track_path), args.cover, args.artist, track_title,
                args.genre, args.context, args.shorts, args.out,
                lyrics_offset=args.lyrics_offset,
                watermark_logo_path=args.watermark_logo,
            )
    else:
        parser.error("Debes indicar --audio o --album-dir")


if __name__ == "__main__":
    main()
