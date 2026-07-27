"""
reprogramar_lp.py — recalcula las fechas de publicación de un LP que YA
tiene vídeos/Shorts subidos a YouTube (con video_id), a partir de un
calendario_lanzamiento.json nuevo — por ejemplo, para adelantar algunos
singles antes que el resto del álbum sin tener que volver a subir nada.

No hace falta acceso a los archivos de vídeo/audio del LP: todo el
contenido (título, descripción, etiquetas) se reutiliza tal cual del
calendario ya existente — solo cambian las fechas de publicación.

Por defecto SOLO SIMULA (no llama a la API de YouTube ni toca el
calendario real): calcula el nuevo calendario, lo compara con el actual y
enseña qué elementos YA SUBIDOS cambiarían de fecha, guardando el
resultado propuesto en un archivo aparte para revisarlo con calma. Con
--apply, además actualiza de verdad el publishAt de cada vídeo/Short ya
subido cuya fecha cambie (llamada real a la API de YouTube) y sobrescribe
el calendario real del LP (con una copia de seguridad del anterior).

Uso:
    Solo simular (por defecto):
    python tools/reprogramar_lp.py calendario_youtube.json calendario_lanzamiento.json

    Aplicar de verdad (actualiza YouTube):
    python tools/reprogramar_lp.py calendario_youtube.json calendario_lanzamiento.json --apply --channel IWT
"""

import argparse
import json
import sys
from datetime import date, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lp_shorts_schedule import MADRID_TZ, _leading_number, _to_local_label, _to_utc  # noqa: E402

SHORT_HOUR_A = time(12, 0)
SHORT_HOUR_B = time(21, 0)


def _pick_backlog_tracks(track_numbers, cursors, lengths, pointer):
    n = len(track_numbers)
    picks = []
    scanned = 0
    p = pointer
    while len(picks) < 2 and scanned < n:
        tn = track_numbers[p % n]
        if cursors[tn] < lengths[tn]:
            picks.append(tn)
        p += 1
        scanned += 1
    return picks, p % n


def rebuild_schedule_from_existing(old_schedule, lp_calendar, main_hour=18, main_minute=0):
    """
    Recalcula el calendario completo (mismas reglas que build_lp_schedule
    de src/lp_shorts_schedule.py) pero reutilizando el CONTENIDO (título/
    descripción/etiquetas/rutas) ya presente en `old_schedule`, sin leer
    nada de disco -- así funciona igual desde cualquier máquina, tenga o
    no acceso a los archivos de vídeo/audio reales del LP.
    """
    by_number = {}
    for item in old_schedule:
        tn = item["track_number"]
        by_number.setdefault(tn, {"main": None, "shorts": []})
        if item["kind"] == "main":
            by_number[tn]["main"] = item
        else:
            by_number[tn]["shorts"].append(item)
    # se recupera el orden relativo original de los Shorts de cada tema
    # ordenando por su publish_at_utc ANTERIOR -- así se conserva la
    # secuencia real con la que se generaron (sin repetir clip/mejor
    # momento), no un orden arbitrario de aparición en el archivo.
    for tn in by_number:
        by_number[tn]["shorts"].sort(key=lambda i: i["publish_at_utc"])

    release_order = sorted(lp_calendar, key=lambda c: c["youtube_start_date"])
    release_track_numbers = [_leading_number(e["track"]) for e in release_order]
    release_dates = [date.fromisoformat(e["youtube_start_date"]) for e in release_order]

    missing = [tn for tn in release_track_numbers if tn not in by_number]
    if missing:
        raise ValueError(f"El calendario ya subido no tiene ningún elemento para el/los tema(s) {missing}")

    schedule = []
    for tn, rdate in zip(release_track_numbers, release_dates):
        main_old = by_number[tn]["main"]
        schedule.append({
            "kind": "main",
            "track_number": tn,
            "video_path": main_old["video_path"],
            "meta_path": main_old["meta_path"],
            "title": main_old["title"],
            "description": main_old["description"],
            "tags_youtube": main_old["tags_youtube"],
            "publish_at_local": _to_local_label(rdate, time(main_hour, main_minute)),
            "publish_at_utc": _to_utc(rdate, time(main_hour, main_minute)),
        })

    cursors = {tn: 0 for tn in release_track_numbers}
    lengths = {tn: len(by_number[tn]["shorts"]) for tn in release_track_numbers}

    def _pop_short(tn):
        i = cursors[tn]
        if i >= lengths[tn]:
            return None
        cursors[tn] += 1
        return by_number[tn]["shorts"][i]

    day = release_dates[0]
    backlog_pointer = 0

    while True:
        released_idx = [i for i, d in enumerate(release_dates) if d <= day]
        if not released_idx:
            day += timedelta(days=1)
            continue

        current_idx = released_idx[-1]
        has_next = current_idx + 1 < len(release_track_numbers)

        if not has_next:
            total_remaining = sum(lengths[tn] - cursors[tn] for tn in release_track_numbers)
            if total_remaining == 0:
                break

        day_picks = []
        if has_next:
            current_track = release_track_numbers[current_idx]
            next_track = release_track_numbers[current_idx + 1]
            picked_a = _pop_short(current_track)
            if picked_a:
                day_picks.append((SHORT_HOUR_A, current_track, picked_a))
            picked_b = _pop_short(next_track)
            if picked_b:
                day_picks.append((SHORT_HOUR_B, next_track, picked_b))
        else:
            chosen, backlog_pointer = _pick_backlog_tracks(release_track_numbers, cursors, lengths, backlog_pointer)
            for hour, tn in zip((SHORT_HOUR_A, SHORT_HOUR_B), chosen):
                picked = _pop_short(tn)
                if picked:
                    day_picks.append((hour, tn, picked))

        for hour, tn, old_item in day_picks:
            schedule.append({
                "kind": "short",
                "track_number": tn,
                "video_path": old_item["video_path"],
                "meta_path": old_item["meta_path"],
                "title": old_item["title"],
                "description": old_item["description"],
                "tags_youtube": old_item["tags_youtube"],
                "publish_at_local": _to_local_label(day, hour),
                "publish_at_utc": _to_utc(day, hour),
            })
        day += timedelta(days=1)

    schedule.sort(key=lambda i: i["publish_at_utc"])
    return schedule


_CARRY_OVER_FIELDS = ("video_id", "comment_id", "in_shorts_playlist", "linked_next")


def merge_schedules(old_schedule, new_schedule):
    """
    Traslada el estado de subida (video_id, comment_id...) del calendario
    viejo al nuevo, emparejando por `video_path` (identificador estable:
    el archivo generado no cambia, solo su fecha de publicación). Devuelve
    (nuevo_calendario_fusionado, lista_de_cambios) -- cada cambio es un
    elemento YA SUBIDO cuya fecha de publicación programada se movería.
    """
    old_by_path = {item["video_path"]: item for item in old_schedule}
    changes = []
    for new_item in new_schedule:
        old_item = old_by_path.get(new_item["video_path"])
        if not old_item:
            continue
        for field in _CARRY_OVER_FIELDS:
            if field in old_item:
                new_item[field] = old_item[field]
        if old_item.get("video_id") and old_item["publish_at_utc"] != new_item["publish_at_utc"]:
            changes.append({
                "video_id": old_item["video_id"],
                "kind": new_item["kind"],
                "track_number": new_item["track_number"],
                "title": new_item["title"],
                "old_publish_at": old_item["publish_at_utc"],
                "new_publish_at": new_item["publish_at_utc"],
            })
    return new_schedule, changes


def print_report(old_schedule, new_schedule, changes):
    old_with_id = {i["video_path"] for i in old_schedule if i.get("video_id")}
    new_paths = {i["video_path"] for i in new_schedule}
    orphaned = old_with_id - new_paths  # ya subidos que desaparecen del nuevo calendario (no debería pasar nunca)

    print(f"Elementos en el calendario nuevo: {len(new_schedule)} (antes: {len(old_schedule)})")
    print(f"Ya subidos que cambiarían de fecha: {len(changes)}")
    if orphaned:
        print(f"¡AVISO! {len(orphaned)} elementos ya subidos no aparecen en el calendario nuevo -- revisar antes de aplicar nada.")

    changes_by_track = {}
    for c in changes:
        entry = changes_by_track.setdefault(c["track_number"], {"main": 0, "short": 0})
        entry[c["kind"]] += 1
    print("\nCambios por tema:")
    for tn in sorted(changes_by_track):
        c = changes_by_track[tn]
        print(f"  Tema {tn}: {c['main']} vídeo(s) principal(es), {c['short']} short(s)")

    print("\nVídeos principales que cambian de fecha:")
    for c in changes:
        if c["kind"] == "main":
            print(f"  Tema {c['track_number']} ({c['title'][:50]}): {c['old_publish_at']} -> {c['new_publish_at']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("calendario_youtube", help="Ruta al calendario_youtube.json YA subido")
    parser.add_argument("calendario_lanzamiento", help="Ruta al calendario_lanzamiento.json NUEVO")
    parser.add_argument("--out", default=None, help="Dónde guardar el calendario propuesto (por defecto, junto al de entrada)")
    parser.add_argument("--main-hour", type=int, default=18, help="Hora (España) de publicación de los vídeos principales")
    parser.add_argument("--apply", action="store_true", help="Aplica de verdad los cambios en YouTube (por defecto solo simula)")
    parser.add_argument("--channel", default=None, help="Canal de YouTube a usar (ver src/youtube_uploader._token_path_for)")
    args = parser.parse_args()

    old_path = Path(args.calendario_youtube)
    old_schedule = json.loads(old_path.read_text(encoding="utf-8"))
    lp_calendar = json.loads(Path(args.calendario_lanzamiento).read_text(encoding="utf-8"))

    new_schedule = rebuild_schedule_from_existing(old_schedule, lp_calendar, main_hour=args.main_hour)
    new_schedule, changes = merge_schedules(old_schedule, new_schedule)

    print_report(old_schedule, new_schedule, changes)

    out_path = Path(args.out) if args.out else old_path.with_name(old_path.stem + "_propuesto.json")
    out_path.write_text(json.dumps(new_schedule, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nCalendario propuesto guardado en: {out_path}")

    if not args.apply:
        print("\nModo simulación: no se ha llamado a la API de YouTube ni se ha tocado el calendario real.")
        print("Revisa el archivo propuesto y, cuando lo confirmes, relanza con --apply.")
        return

    print(f"\n--apply activado: actualizando {len(changes)} elemento(s) ya subido(s) en YouTube...")
    from src.youtube_uploader import update_video_schedule  # noqa: E402

    backup_path = old_path.with_suffix(".json.bak")
    backup_path.write_text(old_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Copia de seguridad del calendario anterior: {backup_path}")

    done = 0
    for c in changes:
        try:
            update_video_schedule(c["video_id"], c["new_publish_at"], channel=args.channel)
            done += 1
            print(f"  OK: {c['kind']} tema {c['track_number']} ({c['video_id']}) -> {c['new_publish_at']}")
        except Exception as e:
            print(f"  ERROR actualizando {c['video_id']}: {e}")

    old_path.write_text(json.dumps(new_schedule, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{done}/{len(changes)} elementos actualizados en YouTube. Calendario real actualizado: {old_path}")


if __name__ == "__main__":
    main()
