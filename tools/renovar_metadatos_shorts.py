"""
renovar_metadatos_shorts.py — regenera título/descripción/hashtags/tags de
los Shorts de un LP que TODAVÍA NO se han subido a YouTube (los que ya
tienen video_id se dejan completamente intactos: no tocarlos no arriesga
nada de lo ya publicado ni gasta cuota de la API de YouTube en vano).

Por qué hace falta: antes del arreglo en src/metadata_generator.py, los
Shorts de un mismo tema podían compartir literalmente el mismo puñado de
hashtags docenas de veces seguidas -- justo el patrón que YouTube trata
como contenido repetitivo y penaliza en alcance. Este script agrupa los
Shorts pendientes por tema (una sola llamada a la API por tema, no una
por Short) y les asigna metadatos nuevos y variados entre sí, usando el
mismo generador ya corregido que se usa para Shorts nuevos.

Uso:
    python tools/renovar_metadatos_shorts.py "MUSICA\\It Was Time\\The Hollow Hour" "lp_content\\The_Hollow_Hour"
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from src.lp_shorts_schedule import _leading_number, _with_hashtags, load_lp_schedule, save_lp_schedule
from src.metadata_generator import generate_short_metadata_pool

ARTIST = "It Was Time"
GENRE = (
    "Rock progresivo atmosférico, producción fría y distante, estética "
    "fotográfica analógica desaturada, nunca cálida ni pulida"
)
MAX_POOL_SIZE = 30  # tope razonable de variantes pedidas de una vez por tema


def _track_titles(lp_calendar_path: Path) -> dict:
    lp_calendar = json.loads(lp_calendar_path.read_text(encoding="utf-8"))
    titles = {}
    for entry in lp_calendar:
        tn = _leading_number(entry["track"])
        titles[tn] = entry["track"].split(".", 1)[1].strip()
    return titles


def _context_for_track(lp_content_dir: Path, track_number: int) -> str:
    matches = list(lp_content_dir.glob(f"{track_number:02d}_*/contexto.txt"))
    if not matches:
        raise FileNotFoundError(
            f"No encuentro contexto.txt para el tema {track_number} en {lp_content_dir}"
        )
    return matches[0].read_text(encoding="utf-8").strip()


def main():
    if len(sys.argv) < 3:
        print(f"Uso: python {Path(__file__).name} <carpeta_del_LP> <carpeta_lp_content>")
        sys.exit(1)

    lp_dir = Path(sys.argv[1])
    lp_content_dir = Path(sys.argv[2])
    schedule_path = lp_dir / "calendario_youtube.json"
    lp_calendar_path = lp_content_dir / "calendario_lanzamiento.json"

    schedule = load_lp_schedule(schedule_path)
    track_titles = _track_titles(lp_calendar_path)

    pending_by_track = {}
    for item in schedule:
        if item["kind"] != "short" or item.get("video_id"):
            continue
        pending_by_track.setdefault(item["track_number"], []).append(item)

    if not pending_by_track:
        print("No hay ningún Short pendiente de subir -- nada que renovar.")
        return

    backup_path = schedule_path.with_name(schedule_path.stem + ".json.bak")
    if not backup_path.exists():
        backup_path.write_text(schedule_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Copia de seguridad del calendario anterior: {backup_path}")

    total_renewed = 0
    for track_number, items in sorted(pending_by_track.items()):
        track_title = track_titles.get(track_number)
        if not track_title:
            print(f"Aviso: no encuentro el título del tema {track_number} en calendario_lanzamiento.json, lo salto.")
            continue
        context = _context_for_track(lp_content_dir, track_number)

        n = min(len(items), MAX_POOL_SIZE)
        print(f"-> Tema {track_number} ({track_title}): pidiendo {n} variantes nuevas para {len(items)} Shorts pendientes...")
        pool = generate_short_metadata_pool(ARTIST, track_title, GENRE, context, n=n)

        for i, item in enumerate(items):
            variant = pool[i % len(pool)]
            item["title"] = variant["title"]
            item["tags_youtube"] = variant["tags_youtube"]
            item["description"] = _with_hashtags(variant)

            meta_path = Path(item["meta_path"])
            if meta_path.exists():
                meta_path.write_text(json.dumps(variant, ensure_ascii=False, indent=2), encoding="utf-8")

            total_renewed += 1

        save_lp_schedule(schedule, schedule_path)
        print(f"   {len(items)} Shorts del tema {track_number} renovados y guardados.")

    print(f"\n-> {total_renewed} Shorts pendientes renovados en total. Los ya subidos a YouTube no se han tocado.")


if __name__ == "__main__":
    main()
