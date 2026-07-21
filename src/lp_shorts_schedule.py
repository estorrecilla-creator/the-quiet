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

El CALENDARIO se calcula todo de una vez: el resultado son las fechas
exactas de publicación de cada vídeo/Short, que `upload_lp_schedule` sube
oculto con su `publishAt` ya fijado. La SUBIDA en sí, en cambio, sí hay que
repartirla en varios días — la cuota gratuita de la API de YouTube (10.000
unidades/día) solo da para ~5-6 vídeos subidos al día, muy por debajo de
los ~550 vídeos de un LP — así que `upload_lp_schedule` sube los que le
caben en la cuota del día y se para solo, sin duplicar nada ni perder el
sitio: basta con relanzar la misma fase en días sucesivos hasta terminar.
"""

import json
import re
from datetime import date, datetime, time, timedelta, timezone
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


def _is_published(publish_at_utc: str) -> bool:
    """Ya pasó su fecha de publicación programada -> el vídeo debería ser
    público de verdad. Antes de eso, YouTube rechaza crear comentarios en
    él (sigue siendo privado aunque la subida en sí haya ido bien)."""
    dt = datetime.strptime(publish_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= dt


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


# Costes aproximados en unidades de cuota de la API de YouTube (no son
# exactos al 100%, pero de sobra para no pasarnos): subir un vídeo cuesta
# 1600, ponerle miniatura 50, añadirlo a una lista de reproducción 50,
# actualizar su descripción ~50, publicar un comentario ~50. La cuota
# gratuita por defecto es 10.000 unidades/día — con eso solo caben ~5-6
# vídeos subidos al día.
COST_VIDEO_INSERT = 1600
COST_THUMBNAIL_SET = 50
COST_PLAYLIST_INSERT = 50
COST_VIDEO_UPDATE = 50
COST_COMMENT_INSERT = 50
DEFAULT_DAILY_QUOTA_BUDGET = 9000  # margen de seguridad bajo las 10.000 de por defecto


def _is_quota_error(exc) -> bool:
    from googleapiclient.errors import HttpError
    if not isinstance(exc, HttpError):
        return False
    reason = ""
    try:
        reason = (exc.error_details[0].get("reason", "") if exc.error_details else "")
    except (AttributeError, IndexError, TypeError):
        pass
    text = f"{reason} {exc}".lower()
    return "quota" in text or "dailylimit" in text


def upload_lp_schedule(
    schedule, save_path, thumbnails=None, playlist_id=None, shorts_playlist_id=None,
    youtube=None, link_block: str = "", idioma: str = None, track_positions=None,
    daily_quota_budget: int = DEFAULT_DAILY_QUOTA_BUDGET,
):
    """
    Sube (programada) cada elemento de `schedule`, guardando el progreso
    tras cada subida — si se corta a mitad, al relanzarlo se salta lo ya
    subido en vez de duplicarlo. `thumbnails`: dict {número_de_tema: ruta_
    miniatura} — la MISMA miniatura del tema se reutiliza para su vídeo
    principal y todos sus Shorts.

    El orden de SUBIDA no afecta cuándo se publica de verdad cada vídeo
    (eso lo fija `publishAt`), así que se prioriza tener el álbum entero
    disponible en el canal cuanto antes: primero se suben TODOS los
    vídeos principales de los 12 temas, y solo después los Shorts — si
    no, con la cuota diaria y subiendo tema a tema completo (vídeo + sus
    ~45 Shorts) antes de pasar al siguiente, el último tema podría tardar
    semanas en tener su vídeo principal arriba. Dentro de los Shorts, se
    suben en el mismo orden en que están programados para publicarse
    (por fecha), no agrupados por tema — si no, un Short con fecha de
    publicación cercana podría no estar subido todavía porque el tema
    anterior aún no ha terminado de subir los suyos.

    Para mantener al oyente el mayor tiempo posible escuchando la música
    (no solo viendo Shorts sueltos), enlaza:
    - Cada Short con el vídeo principal de SU tema ("escucha el tema
      completo") — como los vídeos principales van todos primero, el
      enlace ya está listo sin tener que volver a tocar cada Short
      después.
    - Cada vídeo principal con el SIGUIENTE tema del álbum en orden
      narrativo (para encadenar la escucha de todo el disco), en una
      segunda pasada — solo sobre los vídeos principales (pocos), no
      sobre los Shorts, para no multiplicar las llamadas a la API.

    Un LP entero (~550 vídeos) no cabe en la cuota diaria gratuita de la
    API de YouTube (10.000 unidades/día, ~5-6 vídeos), así que esta
    función sube los que le caben en `daily_quota_budget` y se para sola
    —sin error, sin perder el sitio— en cuanto se acerca al límite (o en
    cuanto Google la rechaza de verdad por cuota, como red de seguridad
    extra). Basta con volver a llamarla (relanzando esta fase desde
    `procesar_lp.py`) en días sucesivos hasta terminar.
    """
    from src.youtube_uploader import upload_video, update_video_description

    thumbnails = thumbnails or {}
    track_positions = track_positions or {}
    quota_used = 0
    quota_exhausted = False

    def _estimate_cost(item):
        cost = COST_VIDEO_INSERT + COST_COMMENT_INSERT
        if thumbnails.get(item["track_number"]):
            cost += COST_THUMBNAIL_SET
        if playlist_id and item["kind"] == "main":
            cost += COST_PLAYLIST_INSERT
        if shorts_playlist_id and item["kind"] == "short":
            cost += COST_PLAYLIST_INSERT
        return cost

    def _get_youtube():
        nonlocal youtube
        if youtube is None:
            from src.youtube_uploader import get_authenticated_service
            youtube = get_authenticated_service()
        return youtube

    def _upload_item(item, extra_description=""):
        nonlocal quota_used, quota_exhausted
        if item.get("video_id"):
            print(f"-> {Path(item['video_path']).name} ya estaba subido, lo salto.")
            return
        if quota_exhausted:
            return
        cost = _estimate_cost(item)
        if quota_used + cost > daily_quota_budget:
            quota_exhausted = True
            return

        print(f"\n-> Subiendo {Path(item['video_path']).name} (programado para {item['publish_at_local']})...")
        thumbnail_path = thumbnails.get(item["track_number"])
        try:
            video_id = upload_video(
                video_path=item["video_path"],
                title=item["title"],
                description=item["description"] + link_block + extra_description,
                tags=item["tags_youtube"],
                publish_at=item["publish_at_utc"],
                thumbnail_path=thumbnail_path,
                default_language=idioma,
            )
        except Exception as e:
            if _is_quota_error(e):
                print("   Cuota de YouTube agotada de verdad (Google lo ha rechazado) — paro aquí por hoy.")
                quota_exhausted = True
                return
            raise
        item["video_id"] = video_id
        quota_used += cost
        save_lp_schedule(schedule, save_path)
        if playlist_id and item["kind"] == "main":
            from src.youtube_playlists import add_video_to_playlist
            position = track_positions.get(item["track_number"])
            add_video_to_playlist(youtube, playlist_id, video_id, position=position)
            print(f"-> Añadido a la lista de reproducción (posición {position}).")
        if shorts_playlist_id and item["kind"] == "short":
            from src.youtube_playlists import add_video_to_playlist
            add_video_to_playlist(youtube, shorts_playlist_id, video_id)
            item["in_shorts_playlist"] = True
            print("-> Añadido a la lista de reproducción de Shorts.")

        # el comentario NO se intenta aquí: el vídeo se sube programado
        # (publishAt futuro) y sigue siendo privado hasta esa fecha —
        # YouTube rechaza crear comentarios en un vídeo todavía privado
        # ("403 forbidden"), así que intentarlo justo al subir fallaría
        # siempre. Se publica más abajo, en la pasada de comentarios
        # pendientes, que solo actúa sobre vídeos ya públicos de verdad
        # (y se puede relanzar cualquier día para ir cogiendo los que se
        # hayan ido publicando desde la última vez).

    track_numbers = sorted({item["track_number"] for item in schedule})
    main_video_id_by_track = {}

    # 1. Todos los vídeos principales primero, de todos los temas — para
    #    que el álbum entero esté disponible en el canal cuanto antes, en
    #    vez de quedar los últimos temas bloqueados detrás de los ~45
    #    Shorts de cada uno de los temas anteriores (con la cuota diaria,
    #    subir un tema entero -vídeo + Shorts- antes de pasar al
    #    siguiente tardaría semanas en llegar al último tema).
    for tn in track_numbers:
        if quota_exhausted:
            break
        main_item = next(
            (i for i in schedule if i["track_number"] == tn and i["kind"] == "main"), None,
        )
        if main_item:
            _upload_item(main_item)
            if main_item.get("video_id"):
                main_video_id_by_track[tn] = main_item["video_id"]

    # 2. Luego los Shorts, EN EL MISMO ORDEN EN QUE SE VAN A PUBLICAR de
    #    verdad (por publish_at_utc), no agrupados por tema uno detrás de
    #    otro — si no, un Short de un tema que le toque publicarse pronto
    #    podría quedarse sin subir todavía porque el tema anterior (con
    #    sus ~45 Shorts propios) no ha terminado aún de subirse. El
    #    calendario mezcla temas por fecha real de publicación (día a
    #    día, con más de un tema a la vez), así que subir en ese mismo
    #    orden es lo único que garantiza no quedarse atrás de ninguno.
    all_shorts = sorted(
        (i for i in schedule if i["kind"] == "short"),
        key=lambda i: i["publish_at_utc"],
    )
    for item in all_shorts:
        if quota_exhausted:
            break
        main_id = main_video_id_by_track.get(item["track_number"])
        watch_full_link = (
            f"\n\n🎧 Escucha el tema completo: https://youtu.be/{main_id}" if main_id else ""
        )
        _upload_item(item, extra_description=watch_full_link)

    if not quota_exhausted or quota_used + COST_VIDEO_UPDATE <= daily_quota_budget:
        sorted_tracks = sorted(main_video_id_by_track.keys())
        for i, tn in enumerate(sorted_tracks[:-1]):
            main_item = next(
                (it for it in schedule if it["track_number"] == tn and it["kind"] == "main"), None,
            )
            if not main_item or not main_item.get("video_id") or main_item.get("linked_next"):
                continue
            if quota_used + COST_VIDEO_UPDATE > daily_quota_budget:
                break
            next_id = main_video_id_by_track[sorted_tracks[i + 1]]
            full_description = (
                main_item["description"] + link_block
                + f"\n\n▶ Sigue escuchando: https://youtu.be/{next_id}"
            )
            try:
                update_video_description(main_item["video_id"], full_description)
            except Exception as e:
                if _is_quota_error(e):
                    break
                raise
            main_item["linked_next"] = True
            quota_used += COST_VIDEO_UPDATE
            save_lp_schedule(schedule, save_path)
            print(f"-> Tema {tn} enlazado con el siguiente del álbum.")

    # 4. Comentarios pendientes: vídeos ya subidos y YA públicos de
    #    verdad (pasó su publish_at_utc) que todavía no tienen comentario
    #    — normal que haya varios, ya que al subirlos seguían privados/
    #    programados. Se puede (y debe) relanzar cada día para ir
    #    cogiendo los que se vayan publicando desde la última vez.
    if not quota_exhausted or quota_used + COST_COMMENT_INSERT <= daily_quota_budget:
        for item in schedule:
            if quota_used + COST_COMMENT_INSERT > daily_quota_budget:
                break
            if not item.get("video_id") or item.get("comment_id"):
                continue
            if not _is_published(item["publish_at_utc"]):
                continue
            if item["kind"] == "short":
                main_id = main_video_id_by_track.get(item["track_number"])
                extra = f"\n\n🎧 Escucha el tema completo: https://youtu.be/{main_id}" if main_id else ""
            else:
                extra = ""
            comment_text = (extra + link_block).strip()
            if not comment_text:
                continue
            try:
                from src.youtube_comments import post_comment
                item["comment_id"] = post_comment(_get_youtube(), item["video_id"], comment_text)
                quota_used += COST_COMMENT_INSERT
                save_lp_schedule(schedule, save_path)
                print(
                    f"-> Comentario publicado en {Path(item['video_path']).name} "
                    "(recuerda fijarlo tú si quieres verlo arriba de todo — eso no lo puede hacer la API)."
                )
            except Exception as e:
                print(f"   Aviso: no se pudo publicar el comentario de {Path(item['video_path']).name} ({e}).")

    # 5. Por si algún Short ya estaba subido de antes de que existiera su
    #    lista de reproducción (o de que se creara para este LP en
    #    concreto): se añaden ahora, cada uno una sola vez.
    if shorts_playlist_id:
        for item in schedule:
            if quota_used + COST_PLAYLIST_INSERT > daily_quota_budget:
                break
            if item["kind"] != "short" or not item.get("video_id") or item.get("in_shorts_playlist"):
                continue
            try:
                from src.youtube_playlists import add_video_to_playlist
                add_video_to_playlist(_get_youtube(), shorts_playlist_id, item["video_id"])
                item["in_shorts_playlist"] = True
                quota_used += COST_PLAYLIST_INSERT
                save_lp_schedule(schedule, save_path)
            except Exception as e:
                print(f"   Aviso: no se pudo añadir {Path(item['video_path']).name} a la lista de Shorts ({e}).")

    total = len(schedule)
    subidos = sum(1 for i in schedule if i.get("video_id"))
    if subidos < total:
        print(
            f"\n-> Subidos {subidos}/{total} por hoy (cuota diaria de YouTube agotada). "
            "Vuelve a lanzar esta fase de nuevo (hoy más tarde o cualquier otro día) "
            "para seguir — no se duplica nada, retoma donde lo hemos dejado."
        )
    else:
        print(f"\n-> Los {total} vídeos del LP están subidos.")

    return schedule
