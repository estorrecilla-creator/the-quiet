"""
subir_shorts_tema.py — sube a YouTube todos los Shorts de un tema suelto
(los que genera subir_tema.py / process_track: short_01.mp4, short_02.mp4...),
usando el pool de variantes de metadatos ya escrito en un JSON con la misma
forma que espera src.metadata_generator.load_metadata_cache() (clave
"shorts_pool" -> {"Título del tema": [ {"title", "description", "hashtags",
"tags_youtube"}, ... ]}). Las variantes se van repartiendo cíclicamente
entre los Shorts encontrados (si hay más Shorts que variantes, se repiten).

Sube como PRIVADO por defecto (revisar antes de publicar), igual que el
resto del pipeline.

Uso:
    python tools/subir_shorts_tema.py "output/The_Signature" \
        --metadata config/metadata_the_signature.json --title "The Signature" \
        --channel reichskonkordat

    ... --publish-now
    ... --publish-date 2026-08-14 --publish-time 18:00
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

SHORT_GLOB = "short_*.mp4"


def _build_description(meta):
    description = meta["description"].rstrip()
    if meta.get("hashtags"):
        description += "\n\n" + " ".join(meta["hashtags"])
    return description


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("shorts_dir", help="Carpeta con los short_NN.mp4 generados por subir_tema.py")
    parser.add_argument("--metadata", required=True, help="Ruta al JSON de metadatos (misma forma que espera load_metadata_cache)")
    parser.add_argument("--title", required=True, help="Título del tema, tal cual está como clave dentro de \"shorts_pool\" en el JSON")
    parser.add_argument("--language", default="en", help="Idioma de los Shorts (ej. en, es)")
    parser.add_argument("--publish-now", action="store_true", help="Subir directamente como público, en vez de privado para revisar antes")
    parser.add_argument("--publish-date", default=None, help="Fecha de publicación programada (misma para todos), hora de España (ej. 2026-08-14)")
    parser.add_argument("--publish-time", default="18:00", help="Hora de publicación programada, hora de España (por defecto 18:00)")
    parser.add_argument("--channel", default=None, help="Canal de YouTube a usar, si hace falta (ver src/youtube_uploader._token_path_for)")
    args = parser.parse_args()

    shorts_dir = Path(args.shorts_dir)
    if not shorts_dir.is_dir():
        print(f"No encuentro la carpeta: {args.shorts_dir}")
        sys.exit(1)

    shorts = sorted(shorts_dir.glob(SHORT_GLOB))
    if not shorts:
        print(f"No encuentro ningún {SHORT_GLOB} dentro de {args.shorts_dir}.")
        sys.exit(1)

    metadata_path = Path(args.metadata)
    if not metadata_path.exists():
        print(f"No encuentro el archivo de metadatos: {args.metadata}")
        sys.exit(1)
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    variants = data.get("shorts_pool", {}).get(args.title)
    if not variants:
        disponibles = ", ".join(data.get("shorts_pool", {}).keys()) or "(ninguno)"
        print(f"No hay variantes de Shorts para \"{args.title}\" en {args.metadata} (clave \"shorts_pool\").")
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

    privacy_status = "public" if args.publish_now else "private"
    print(f"-> {len(shorts)} Shorts encontrados, {len(variants)} variantes de metadatos disponibles.")

    for i, short_path in enumerate(shorts):
        meta = variants[i % len(variants)]
        print(f"\n[{i + 1}/{len(shorts)}] {short_path.name}")
        print(f"   Título: {meta['title']}")
        video_id = upload_video(
            video_path=str(short_path),
            title=meta["title"],
            description=_build_description(meta),
            tags=meta.get("tags_youtube", []),
            privacy_status=privacy_status,
            publish_at=publish_at,
            default_language=args.language,
            channel=args.channel,
        )
        print(f"   Subido: https://youtube.com/watch?v={video_id}")

    print(f"\nListo -- {len(shorts)} Shorts subidos como {privacy_status}"
          + (f", programados para el {args.publish_date} a las {args.publish_time} (hora de España)." if publish_at else "."))
    if privacy_status == "private" and not publish_at:
        print("Revísalos en YouTube Studio y cámbialos a Público cuando estés conforme.")


if __name__ == "__main__":
    main()
