"""
subir_video_tema.py — sube a YouTube el vídeo principal de un tema suelto
(el que genera subir_tema.py / process_track), usando los metadatos ya
escritos en un JSON con la misma forma que espera
src.metadata_generator.load_metadata_cache() (clave "main" ->
{"Título del tema": {"title", "description", "hashtags", "tags_youtube"}}).

Sube como PRIVADO por defecto (revisar antes de publicar), igual que el
resto del pipeline.

Uso:
    python tools/subir_video_tema.py "output/The_Signature/main_video.mp4" \
        --metadata config/metadata_the_signature.json --title "The Signature"

    ... --publish-now
    ... --publish-date 2026-08-07 --publish-time 20:00
    ... --channel reichskonkordat
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from src.youtube_uploader import upload_video


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video_path")
    parser.add_argument("--metadata", required=True, help="Ruta al JSON de metadatos (misma forma que espera load_metadata_cache)")
    parser.add_argument("--title", required=True, help="Título del tema, tal cual está como clave dentro de \"main\" en el JSON")
    parser.add_argument("--language", default="en", help="Idioma del vídeo (ej. en, es) -- ayuda a YouTube a mostrarlo a la audiencia correcta")
    parser.add_argument("--publish-now", action="store_true", help="Subir directamente como público, en vez de privado para revisar antes")
    parser.add_argument("--publish-date", default=None, help="Fecha de publicación programada, hora de España (ej. 2026-08-07)")
    parser.add_argument("--publish-time", default="20:00", help="Hora de publicación programada, hora de España (por defecto 20:00)")
    parser.add_argument("--channel", default=None, help="Canal de YouTube a usar, si hace falta (ver src/youtube_uploader._token_path_for)")
    args = parser.parse_args()

    if not Path(args.video_path).exists():
        print(f"No encuentro el vídeo: {args.video_path}")
        sys.exit(1)

    metadata_path = Path(args.metadata)
    if not metadata_path.exists():
        print(f"No encuentro el archivo de metadatos: {args.metadata}")
        sys.exit(1)
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    meta = data.get("main", {}).get(args.title)
    if not meta:
        disponibles = ", ".join(data.get("main", {}).keys()) or "(ninguno)"
        print(f"No hay metadatos para \"{args.title}\" en {args.metadata} (clave \"main\").")
        print(f"Títulos disponibles ahí: {disponibles}")
        sys.exit(1)

    if args.publish_now and args.publish_date:
        print("No tiene sentido pedir --publish-now y --publish-date a la vez -- elige uno de los dos.")
        sys.exit(1)

    publish_at = None
    if args.publish_date:
        local_dt = datetime.strptime(
            f"{args.publish_date} {args.publish_time}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=ZoneInfo("Europe/Madrid"))
        publish_at = local_dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Los hashtags se añaden al final de la descripción (YouTube los detecta
    # ahí y los muestra sobre el título); "tags_youtube" son las palabras
    # clave sueltas del campo de etiquetas, algo distinto.
    description = meta["description"].rstrip()
    if meta.get("hashtags"):
        description += "\n\n" + " ".join(meta["hashtags"])

    privacy_status = "public" if args.publish_now else "private"
    print(f"-> Subiendo como {privacy_status}: {Path(args.video_path).name}")
    print(f"   Título: {meta['title']}")
    if publish_at:
        print(f"   Programado para el {args.publish_date} a las {args.publish_time} (hora de España) -> {publish_at} UTC")

    video_id = upload_video(
        video_path=args.video_path,
        title=meta["title"],
        description=description,
        tags=meta.get("tags_youtube", []),
        privacy_status=privacy_status,
        publish_at=publish_at,
        default_language=args.language,
        channel=args.channel,
    )
    print(f"\n-> Subido: https://youtube.com/watch?v={video_id}")
    if publish_at:
        print(f"   Se publicará solo el {args.publish_date} a las {args.publish_time} (hora de España) -- hasta entonces sigue en privado.")
    elif privacy_status == "private":
        print("   Está en PRIVADO -- revísalo en YouTube Studio y cámbialo a Público cuando estés conforme.")


if __name__ == "__main__":
    main()
