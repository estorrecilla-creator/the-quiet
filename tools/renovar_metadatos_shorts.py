"""
renovar_metadatos_shorts.py — regenera título/descripción/hashtags/tags de
los Shorts de un LP que TODAVÍA NO son públicos de verdad (ni los que aún
no se han subido a YouTube, ni los que ya están subidos pero siguen
privados esperando su fecha de publicación programada). Los que YA son
públicos de verdad se dejan completamente intactos.

Por qué hace falta: antes del arreglo en src/metadata_generator.py, los
Shorts de un mismo tema podían compartir literalmente el mismo puñado de
hashtags docenas de veces seguidas -- justo el patrón que YouTube trata
como contenido repetitivo y penaliza en alcance. Este script agrupa los
Shorts afectados por tema (una sola llamada a la API de Claude por tema,
no una por Short) y les asigna metadatos nuevos y variados entre sí:
- Si el Short aún no se ha subido: se actualiza solo el calendario local
  (se subirá con los metadatos nuevos en cuanto le toque).
- Si el Short ya está subido pero sigue privado (esperando publishAt): se
  actualiza también de verdad en YouTube (coste de cuota de la API), y
  solo se guarda el cambio en el calendario local si esa llamada tiene
  éxito -- si la cuota diaria se agota a mitad, se para sola sin mentir
  sobre lo que ha cambiado de verdad, y se puede relanzar otro día para
  seguir donde se dejó (mismo patrón que reprogramar_lp.py).

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

from src.lp_shorts_schedule import _is_published, _is_quota_error, _leading_number, _with_hashtags, load_lp_schedule, save_lp_schedule
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

    config_path = lp_dir / "config_subida_youtube.json"
    channel = None
    if config_path.exists():
        channel = json.loads(config_path.read_text(encoding="utf-8")).get("channel")

    schedule = load_lp_schedule(schedule_path)
    track_titles = _track_titles(lp_calendar_path)

    affected_by_track = {}
    for item in schedule:
        if item["kind"] != "short":
            continue
        if item.get("video_id") and _is_published(item["publish_at_utc"]):
            continue  # ya público de verdad -- no tocar
        affected_by_track.setdefault(item["track_number"], []).append(item)

    if not affected_by_track:
        print("No hay ningún Short pendiente/todavía-privado -- nada que renovar.")
        return

    backup_path = schedule_path.with_name(schedule_path.stem + ".json.bak")
    if not backup_path.exists():
        backup_path.write_text(schedule_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Copia de seguridad del calendario anterior: {backup_path}")

    total_renewed = 0
    total_youtube_updated = 0
    quota_hit = False

    for track_number, items in sorted(affected_by_track.items()):
        if quota_hit:
            break
        track_title = track_titles.get(track_number)
        if not track_title:
            print(f"Aviso: no encuentro el título del tema {track_number} en calendario_lanzamiento.json, lo salto.")
            continue
        context = _context_for_track(lp_content_dir, track_number)

        n = min(len(items), MAX_POOL_SIZE)
        print(f"-> Tema {track_number} ({track_title}): pidiendo {n} variantes nuevas para {len(items)} Shorts afectados...")
        pool = generate_short_metadata_pool(ARTIST, track_title, GENRE, context, n=n)

        for i, item in enumerate(items):
            if quota_hit:
                break
            variant = pool[i % len(pool)]
            new_title = variant["title"]
            new_description = _with_hashtags(variant)
            new_tags = variant["tags_youtube"]

            if item.get("video_id"):
                # ya subido pero todavía privado: hay que actualizarlo de
                # verdad en YouTube -- solo se guarda en local si esa
                # llamada tiene éxito, para no mentir sobre lo que ha
                # cambiado de verdad si la cuota se agota a mitad.
                try:
                    from src.youtube_uploader import update_video_metadata
                    update_video_metadata(
                        item["video_id"], title=new_title, description=new_description,
                        tags=new_tags, channel=channel,
                    )
                except Exception as e:
                    if _is_quota_error(e):
                        print(f"\nLímite diario de YouTube alcanzado de verdad ({e}) -- paro aquí por hoy.")
                        print("Vuelve a lanzar este mismo comando otro día para seguir con el resto.")
                        quota_hit = True
                        break
                    print(f"   Aviso: no se pudo actualizar {item['video_id']} en YouTube ({e}), lo salto.")
                    continue
                total_youtube_updated += 1

            item["title"] = new_title
            item["description"] = new_description
            item["tags_youtube"] = new_tags

            meta_path = Path(item["meta_path"])
            if meta_path.exists():
                meta_path.write_text(json.dumps(variant, ensure_ascii=False, indent=2), encoding="utf-8")

            total_renewed += 1
            save_lp_schedule(schedule, schedule_path)

        if not quota_hit:
            print(f"   {len(items)} Shorts del tema {track_number} renovados y guardados.")

    print(
        f"\n-> {total_renewed} Shorts renovados en total "
        f"({total_youtube_updated} de ellos ya estaban subidos y se han actualizado también en YouTube). "
        "Los ya públicos de verdad no se han tocado."
    )


if __name__ == "__main__":
    main()
