"""
bluesky_schedule.py
Publica en Bluesky los mismos Shorts que ya se suben a YouTube, en el
mismo orden y con las mismas fechas -- reutiliza calendario_youtube.json
como fuente de verdad del calendario (no se recalculan fechas aparte) y
lleva su propio calendario_bluesky.json para no perder el sitio ni
duplicar publicaciones.

Diferencias clave con Instagram (ver src/instagram_schedule.py):
- Bluesky SÍ acepta subir el archivo directamente (uploadBlob) -- no hace
  falta ningún alojamiento público propio como src/cloud_storage.py.
- Tampoco exige ninguna app revisada por la plataforma ni cuenta
  vinculada -- solo una "contraseña de aplicación" de la propia cuenta.
- El texto del post está limitado a 300 caracteres (mucho más corto que
  los 2200 de Instagram), y el vídeo a 100 MB / 3 minutos.
- Como Instagram, no admite programar la publicación vía API: solo se
  publican los elementos cuya fecha ya haya pasado -- pensado para
  relanzarse a diario, como continuar_subida_youtube.py.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MAX_TEXT_LENGTH = 300
MAX_VIDEO_SECONDS = 180
MAX_VIDEO_BYTES = 100 * 1024 * 1024


_CARRY_OVER_FIELDS = ("published", "bluesky_uri", "skipped_reason")


def build_bluesky_schedule_from_youtube(youtube_schedule_path, existing_schedule=None) -> list:
    """
    Crea (o actualiza) el calendario de Bluesky a partir del de YouTube --
    mismas fechas, mismo orden, solo los Shorts. El texto final del post
    (con el sorteo si lo hay) se completa al publicar, no aquí, para
    poder añadir bases de un sorteo aunque se hayan escrito después de
    crear este calendario.

    Está pensada para llamarse en CADA ejecución, no solo la primera vez
    -- si se pasa `existing_schedule` (el calendario de Bluesky ya
    guardado), cada elemento YA publicado (o descartado por exceder los
    límites de Bluesky) conserva su estado tal cual, emparejando por
    `video_path` (identificador estable). Los elementos todavía NO
    publicados, en cambio, siempre adoptan la fecha/descripción más
    reciente de YouTube -- así, si el LP se reprograma más adelante
    (tools/reprogramar_lp.py), este calendario se pone al día solo, sin
    perder ni duplicar lo que ya se hubiera publicado.
    """
    with open(youtube_schedule_path, encoding="utf-8") as f:
        youtube_schedule = json.load(f)

    existing_by_path = {item["video_path"]: item for item in (existing_schedule or [])}

    schedule = []
    for item in youtube_schedule:
        if item["kind"] != "short":
            continue
        entry = {
            "track_number": item["track_number"],
            "video_path": item["video_path"],
            "caption_base": item["description"],
            "publish_at_utc": item["publish_at_utc"],
            "publish_at_local": item["publish_at_local"],
            "bluesky_uri": None,
            "published": False,
        }
        old = existing_by_path.get(item["video_path"])
        if old and old.get("published"):
            entry.update({k: old[k] for k in _CARRY_OVER_FIELDS if k in old})
        schedule.append(entry)
    return schedule


def save_bluesky_schedule(schedule, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)
    return out_path


def load_bluesky_schedule(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _is_due(publish_at_utc: str) -> bool:
    dt = datetime.strptime(publish_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= dt


def _probe_video_info(path: str):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "format=duration:stream=width,height",
         "-of", "json", path],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(out.stdout)
    duration = float(data["format"]["duration"])
    stream = data["streams"][0] if data.get("streams") else {}
    return duration, stream.get("width"), stream.get("height")


def _main_video_link_by_track(youtube_schedule_path) -> dict:
    """
    Lee el calendario de YouTube (en vivo, no el que se guardó al crear
    este calendario de Bluesky) y devuelve, por número de tema, el
    enlace a su vídeo principal YA subido -- así el post siempre enlaza
    con la versión más reciente de ese dato, aunque el vídeo principal
    todavía no estuviera subido cuando se generó calendario_bluesky.json.
    """
    if not youtube_schedule_path or not Path(youtube_schedule_path).exists():
        return {}
    with open(youtube_schedule_path, encoding="utf-8") as f:
        youtube_schedule = json.load(f)
    return {
        it["track_number"]: f"https://youtu.be/{it['video_id']}"
        for it in youtube_schedule
        if it["kind"] == "main" and it.get("video_id")
    }


LINK_LABEL = "🎧 Escucha el tema completo"


def _compose_text(caption_base: str, giveaway_text: str, youtube_link: str, max_length: int):
    """
    Compone el texto priorizando que el enlace al vídeo completo en
    YouTube SIEMPRE quepa entero (es el motivo principal de publicar
    también aquí) -- con solo 300 caracteres de margen en Bluesky, si
    hace falta recortar algo para caber, se recorta la descripción/
    sorteo, nunca el enlace.

    Bluesky no admite markdown ([texto](url)): el texto es siempre plano,
    y un enlace "de verdad" (con texto propio en vez de la URL en crudo)
    se consigue con un "facet" -- un tramo del propio texto, marcado por
    posición en BYTES de su codificación UTF-8 (no por caracteres), que
    se convierte en clicable hacia otra URL. Por eso aquí se devuelve
    (texto, facets) en vez de un único string.
    """
    body = caption_base
    if giveaway_text and giveaway_text.strip():
        body = f"{body}\n\n{giveaway_text.strip()}"

    if not youtube_link:
        return body[:max_length], []

    room_for_body = max_length - len(LINK_LABEL) - 2  # 2 = "\n\n"
    body = body[:max(room_for_body, 0)]
    text = f"{body}\n\n{LINK_LABEL}" if body else LINK_LABEL

    text_bytes = text.encode("utf-8")
    label_bytes = LINK_LABEL.encode("utf-8")
    byte_start = len(text_bytes) - len(label_bytes)
    byte_end = len(text_bytes)
    facets = [{
        "index": {"byteStart": byte_start, "byteEnd": byte_end},
        "features": [{"$type": "app.bsky.richtext.facet#link", "uri": youtube_link}],
    }]
    return text, facets


def _is_rate_limit_error(exc) -> bool:
    """
    Bluesky devuelve HTTP 429 cuando se supera el límite de peticiones --
    a diferencia de Meta, aquí basta con mirar el código de estado, no
    hace falta interpretar el cuerpo del error.
    """
    import requests
    return (
        isinstance(exc, requests.exceptions.HTTPError)
        and exc.response is not None
        and exc.response.status_code == 429
    )


def publish_due_bluesky_items(
    schedule, save_path, handle: str, app_password: str,
    giveaway_text: str = "", youtube_schedule_path=None, max_publishes: int = 10,
):
    """
    Publica cada elemento de `schedule` cuya fecha programada ya haya
    pasado y que todavía no se haya publicado. Guarda el progreso tras
    cada publicación, así que se puede relanzar cualquier día sin
    duplicar nada. `giveaway_text`: igual que en Instagram, se añade al
    texto en el momento de publicar (nunca queda desactualizado para lo
    que todavía no se ha publicado).

    `youtube_schedule_path`: ruta a calendario_youtube.json de este mismo
    LP -- si se indica, cada post enlaza con el vídeo completo de su tema
    en YouTube. Si el vídeo principal de ese tema todavía no está subido,
    se publica sin enlace esta vez (no bloquea nada).
    """
    from src.bluesky_uploader import publish_video_post

    main_links = _main_video_link_by_track(youtube_schedule_path)

    due = [
        item for item in schedule
        if not item.get("published") and _is_due(item["publish_at_utc"])
    ]
    due.sort(key=lambda i: i["publish_at_utc"])

    published_count = 0
    for item in due:
        if published_count >= max_publishes:
            break
        video_path = item["video_path"]
        if not Path(video_path).exists():
            print(f"   Aviso: no encuentro {video_path}, lo salto.")
            continue

        size_bytes = Path(video_path).stat().st_size
        duration, width, height = _probe_video_info(video_path)
        if duration > MAX_VIDEO_SECONDS or size_bytes > MAX_VIDEO_BYTES:
            print(
                f"   Aviso: {Path(video_path).name} ({duration:.1f}s, "
                f"{size_bytes / 1024 / 1024:.1f} MB) supera el límite de Bluesky "
                f"({MAX_VIDEO_SECONDS}s / {MAX_VIDEO_BYTES // 1024 // 1024} MB) -- lo salto."
            )
            item["published"] = True  # no reintentar cada día algo que nunca va a valer
            item["skipped_reason"] = "excede_limite_bluesky"
            save_bluesky_schedule(schedule, save_path)
            continue

        text, facets = _compose_text(
            item["caption_base"], giveaway_text,
            main_links.get(item["track_number"]), MAX_TEXT_LENGTH,
        )

        aspect_ratio = {"width": width, "height": height} if width and height else None

        print(f"\n-> Publicando en Bluesky {Path(video_path).name} (programado para {item['publish_at_local']})...")
        try:
            uri = publish_video_post(handle, app_password, video_path, text, aspect_ratio=aspect_ratio, facets=facets)
        except Exception as e:
            if _is_rate_limit_error(e):
                print(f"   Límite de peticiones de Bluesky alcanzado por hoy ({e}) -- paro aquí.")
                break
            print(f"   Aviso: no se pudo publicar {Path(video_path).name} en Bluesky ({e}).")
            continue

        item["bluesky_uri"] = uri
        item["published"] = True
        published_count += 1
        save_bluesky_schedule(schedule, save_path)

    total = len(schedule)
    publicados = sum(1 for i in schedule if i.get("published"))
    if publicados < total:
        print(f"\n-> Publicados {publicados}/{total} Shorts en Bluesky hasta ahora.")
    else:
        print(f"\n-> Los {total} Shorts de este LP ya están publicados en Bluesky.")

    return schedule
