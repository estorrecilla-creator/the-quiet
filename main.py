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


def process_track(audio_path, cover_path, artist, title, genre, context, n_shorts, out_dir):
    out_dir = Path(out_dir) / title.replace(" ", "_")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Procesando: {title} ===")

    # 1. Vídeo principal
    print("-> Generando vídeo principal...")
    main_video_path = out_dir / "main_video.mp4"
    generate_main_video(audio_path, cover_path, str(main_video_path))

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
        generate_short(audio_path, cover_path, str(short_path), moment["start"], moment["end"])

        short_meta = generate_metadata(artist, title, genre, context, content_type="short")
        with open(out_dir / f"short_{i}_metadata.json", "w", encoding="utf-8") as f:
            json.dump(short_meta, f, ensure_ascii=False, indent=2)

    print(f"=== Listo: {out_dir} ===")
    return out_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", help="Ruta a un único archivo de audio")
    parser.add_argument("--album-dir", help="Carpeta con varias pistas para procesar como LP")
    parser.add_argument("--cover", required=True, help="Ruta a la imagen de portada")
    parser.add_argument("--artist", required=True)
    parser.add_argument("--title", help="Título del tema (obligatorio si usas --audio)")
    parser.add_argument("--genre", required=True)
    parser.add_argument("--context", required=True, help="Contexto/concepto artístico")
    parser.add_argument("--shorts", type=int, default=3, help="Número de shorts a generar por tema")
    parser.add_argument("--out", default="output", help="Carpeta de salida")
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
        )
    elif args.album_dir:
        tracks = sorted(Path(args.album_dir).glob("*.mp3")) + sorted(Path(args.album_dir).glob("*.wav"))
        for track_path in tracks:
            track_title = track_path.stem
            process_track(
                str(track_path), args.cover, args.artist, track_title,
                args.genre, args.context, args.shorts, args.out,
            )
    else:
        parser.error("Debes indicar --audio o --album-dir")


if __name__ == "__main__":
    main()
