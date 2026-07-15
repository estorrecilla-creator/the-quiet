"""
lp_shorts_schedule.py
Calendario de publicación en YouTube de un LP completo: los vídeos
principales en sus fechas de calendario_lanzamiento.json, y los Shorts a
razón de 2 al día (12:00 y 21:00, hora de España), siguiendo las reglas
acordadas con Salva durante el recorrido de todo el flujo:

- Mientras se van publicando los 12 temas del LP: a las 12:00 sale un
  Short del tema YA publicado más reciente (rotando sus clips sin
  repetir ninguno), y a las 21:00 un Short de AVANCE del siguiente tema
  — todavía no disponible en streaming, a propósito: es una excepción
  permanente y deliberada a la regla de "nunca YouTube antes que
  streaming", válida para todos los proyectos futuros, no un error.
- En cuanto los 12 temas están publicados: los dos huecos diarios tiran
  del resto de Shorts sin usar de todos los temas, pero nunca dos del
  mismo tema el mismo día — siempre dos temas distintos, rotando —
  hasta agotar la bolsa completa (con 15 clips x 3 Shorts por tema, unos
  540 Shorts en total, ~9 meses de publicaciones desde el primer single).

Se calcula todo de una vez (nada que relanzar periódicamente): el
resultado son las fechas exactas de publicación de cada vídeo/Short, que
`upload_lp_schedule` sube todo oculto con su `publishAt` ya fijado.
"""

import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

MADRID_TZ = ZoneInfo("Europe/Madrid")
SHORT_HOUR_A = time(12, 0)  # tema ya publicado (o backlog, primer hueco del día)
SHORT_HOUR_B = time(21, 0)  # avance del siguiente tema (o backlog, segundo hueco del día)


def _leading_number(text: str):
    m = re.match(r"^(\d+)", text.strip())
    return int(m.group(1)) if m else None


def _load_meta(meta_path):
    with open(meta_path, encoding="utf-8") as f:
        return json.load(f)


def _with_hashtags(meta):
    description = meta.get("description", "")
    hashtags = meta.get("hashtags", [])
    if hashtags:
        # los 3 primeros hashtags de la descripción son los que YouTube usa
        # para el descubrimiento por nicho, encima del título del vídeo.
        description = description.rstrip() + "\n\n" + " ".join(hashtags)
    return description


def _to_utc(d: date, t: time) -> str:
    local_dt = datetime.combine(d, t, tzinfo=MADRID_TZ)
    return local_dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_local_label(d: date, t: time) -> str:
    return datetime.combine(d, t, tzinfo=MADRID_TZ).strftime("%Y-%m-%d %H:%M (hora España)")


def _pick_backlog_tracks(track_numbers, cursors, lengths, pointer):
    """
    Elige hasta 2 temas DISTINTOS que todavía tengan Shorts sin usar,
    empezando a mirar desde `pointer` y rotando en círculo — así, día a
    día, se reparte el hueco entre todos los temas por igual en vez de
    vaciar siempre los mismos primero. Devuelve (temas_elegidos, nuevo
    pointer) — si solo queda un tema con Shorts, devuelve solo ese.
    """
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


def build_lp_schedule(tracks, lp_calendar, main_hour=18, main_minute=0):
    """
    `tracks`: lista de dicts, uno por tema, cada uno con:
      - "number": número de tema
      - "title": título del tema
      - "main_video" / "main_meta": rutas del vídeo principal y su json
      - "shorts": lista ordenada de (ruta_video, ruta_meta) — ya en el
        orden en que se deben ir consumiendo (sin repetir clip).
    `lp_calendar`: lista de calendario_lanzamiento.json — cada entrada con
    "track" (texto que empieza por el número de tema, ej. "3. Título") y
    "youtube_start_date" (fecha en la que ese tema ya está en streaming).

    Devuelve la lista completa de subidas (vídeos + Shorts), cada una con
    "publish_at_local"/"publish_at_utc" ya calculados.
    """
    by_number = {t["number"]: t for t in tracks}
    release_order = sorted(lp_calendar, key=lambda c: c["youtube_start_date"])
    release_track_numbers = [_leading_number(e["track"]) for e in release_order]
    release_dates = [date.fromisoformat(e["youtube_start_date"]) for e in release_order]

    schedule = []

    # 1. Vídeos principales, cada uno en su fecha de calendario.
    for tn, rdate in zip(release_track_numbers, release_dates):
        track = by_number[tn]
        main_meta = _load_meta(track["main_meta"])
        schedule.append({
            "kind": "main",
            "track_number": tn,
            "video_path": track["main_video"],
            "meta_path": track["main_meta"],
            "title": main_meta.get("title", ""),
            "description": _with_hashtags(main_meta),
            "tags_youtube": main_meta.get("tags_youtube", []),
            "publish_at_local": _to_local_label(rdate, time(main_hour, main_minute)),
            "publish_at_utc": _to_utc(rdate, time(main_hour, main_minute)),
        })

    # 2. Shorts, día a día.
    cursors = {tn: 0 for tn in release_track_numbers}
    lengths = {tn: len(by_number[tn]["shorts"]) for tn in release_track_numbers}

    def _pop_short(track_number):
        i = cursors[track_number]
        if i >= lengths[track_number]:
            return None
        cursors[track_number] += 1
        return by_number[track_number]["shorts"][i]

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

        day_picks = []  # (hora, track_number, (video_path, meta_path))
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
            chosen, backlog_pointer = _pick_backlog_tracks(
                release_track_numbers, cursors, lengths, backlog_pointer
            )
            for hour, tn in zip((SHORT_HOUR_A, SHORT_HOUR_B), chosen):
                picked = _pop_short(tn)
                if picked:
                    day_picks.append((hour, tn, picked))

        for hour, tn, (video_path, meta_path) in day_picks:
            meta = _load_meta(meta_path)
            schedule.append({
                "kind": "short",
                "track_number": tn,
                "video_path": video_path,
                "meta_path": meta_path,
                "title": meta.get("title", ""),
                "description": _with_hashtags(meta),
                "tags_youtube": meta.get("tags_youtube", []),
                "publish_at_local": _to_local_label(day, hour),
                "publish_at_utc": _to_utc(day, hour),
            })

        day += timedelta(days=1)

    schedule.sort(key=lambda i: i["publish_at_utc"])
    return schedule


def save_lp_schedule(schedule, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)
    return out_path


def load_lp_schedule(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def upload_lp_schedule(
    schedule, save_path, thumbnails=None, playlist_id=None, youtube=None,
    link_block: str = "", idioma: str = None, track_positions=None,
):
    """
    Sube (programada) cada elemento de `schedule`, guardando el progreso
    tras cada subida — si se corta a mitad (algo casi seguro subiendo un
    LP entero de golpe), al relanzarlo se salta lo ya subido en vez de
    duplicarlo. `thumbnails`: dict {número_de_tema: ruta_miniatura} — la
    MISMA miniatura del tema se reutiliza para su vídeo principal y todos
    sus Shorts (generada una sola vez, justo tras masterizar ese tema).
    """
    from src.youtube_uploader import upload_video

    thumbnails = thumbnails or {}
    track_positions = track_positions or {}

    for item in schedule:
        if item.get("video_id"):
            print(f"-> {Path(item['video_path']).name} ya estaba subido, lo salto.")
            continue

        print(f"\n-> Subiendo {Path(item['video_path']).name} (programado para {item['publish_at_local']})...")
        thumbnail_path = thumbnails.get(item["track_number"])

        video_id = upload_video(
            video_path=item["video_path"],
            title=item["title"],
            description=item["description"] + link_block,
            tags=item["tags_youtube"],
            publish_at=item["publish_at_utc"],
            thumbnail_path=thumbnail_path,
            default_language=idioma,
        )
        item["video_id"] = video_id
        save_lp_schedule(schedule, save_path)

        if playlist_id and item["kind"] == "main":
            from src.youtube_playlists import add_video_to_playlist
            position = track_positions.get(item["track_number"])
            add_video_to_playlist(youtube, playlist_id, video_id, position=position)
            print(f"-> Añadido a la lista de reproducción (posición {position}).")

    return schedule
