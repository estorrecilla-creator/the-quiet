"""
instagram_schedule.py
Publica en Instagram (como Reels) los mismos Shorts que ya se suben a
YouTube, en el mismo orden y con las mismas fechas -- reutiliza
calendario_youtube.json como fuente de verdad del calendario (no se
recalculan fechas aparte) y lleva su propio calendario_instagram.json
para no perder el sitio ni duplicar publicaciones.

Diferencias clave con YouTube (ver también src/meta_uploader.py):
- Instagram NO admite programar la publicación vía API: hay que llamar a
  publish_instagram_video() en el momento exacto en que toca publicar,
  así que esta función solo publica los elementos cuya fecha YA ha
  pasado -- está pensada para relanzarse a diario, como
  continuar_subida_youtube.py.
- Solo los Shorts (formato vertical, corta duración) valen para Reels --
  los vídeos principales del álbum son demasiado largos para el límite
  de la API de Reels (90s), así que no se incluyen aquí.
- Instagram exige una URL pública del vídeo: se sube temporalmente a
  Cloudflare R2 (src/cloud_storage.py), se publica, y se borra de ahí en
  cuanto Instagram ya lo tiene descargado.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MAX_CAPTION_LENGTH = 2200
MIN_REEL_SECONDS = 5
MAX_REEL_SECONDS = 90


def build_instagram_schedule_from_youtube(youtube_schedule_path) -> list:
    """
    Crea el calendario de Instagram a partir del de YouTube ya calculado
    -- mismas fechas, mismo orden, solo los Shorts (los vídeos
    principales no caben en el límite de 90s de Reels). El texto final
    del pie de foto (con el sorteo si lo hay) se completa al publicar,
    no aquí, para poder añadir bases de un sorteo aunque se hayan escrito
    después de crear este calendario.
    """
    with open(youtube_schedule_path, encoding="utf-8") as f:
        youtube_schedule = json.load(f)

    schedule = []
    for item in youtube_schedule:
        if item["kind"] != "short":
            continue
        schedule.append({
            "track_number": item["track_number"],
            "video_path": item["video_path"],
            "caption_base": item["description"],
            "publish_at_utc": item["publish_at_utc"],
            "publish_at_local": item["publish_at_local"],
            "instagram_media_id": None,
            "published": False,
        })
    return schedule


def save_instagram_schedule(schedule, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)
    return out_path


def load_instagram_schedule(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _is_due(publish_at_utc: str) -> bool:
    dt = datetime.strptime(publish_at_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= dt


def _video_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=30,
    )
    return float(out.stdout.strip())


def _main_video_link_by_track(youtube_schedule_path) -> dict:
    """
    Lee el calendario de YouTube (en vivo, no el que se guardó al crear
    este calendario de Instagram) y devuelve, por número de tema, el
    enlace a su vídeo principal YA subido -- así el Reel siempre enlaza
    con la versión más reciente de ese dato, aunque el vídeo principal
    todavía no estuviera subido cuando se generó calendario_instagram.json.
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


def _compose_caption(caption_base: str, giveaway_text: str, youtube_link: str, max_length: int) -> str:
    """
    Compone el pie de foto priorizando que el enlace al vídeo completo en
    YouTube SIEMPRE quepa entero (es el motivo principal de publicar
    también aquí) -- si hace falta recortar algo para caber en el
    límite, se recorta la descripción/sorteo, nunca el enlace.
    """
    body = caption_base
    if giveaway_text and giveaway_text.strip():
        body = f"{body}\n\n{giveaway_text.strip()}"

    if not youtube_link:
        return body[:max_length]

    link_line = f"🎧 Escucha el tema completo: {youtube_link}"
    room_for_body = max_length - len(link_line) - 2  # 2 = "\n\n"
    body = body[:max(room_for_body, 0)]
    return f"{body}\n\n{link_line}" if body else link_line


def _is_rate_limit_error(exc) -> bool:
    """
    Detecta si Meta ha rechazado la publicación por límite de peticiones
    (no un fallo cualquiera) -- códigos reales de error de la Graph API:
    4 (límite de la app), 17 (límite del usuario), 32 (límite de la
    página), 613 (límite de llamadas a este endpoint). Todos significan
    lo mismo para nosotros: parar por hoy y reintentar en la siguiente
    ejecución diaria, no reventar ni reintentar en bucle.
    """
    import requests
    if not isinstance(exc, requests.exceptions.HTTPError):
        return False
    try:
        code = exc.response.json().get("error", {}).get("code")
    except Exception:
        return False
    return code in (4, 17, 32, 613)


def publish_due_instagram_items(
    schedule, save_path, ig_user_id: str, access_token: str,
    giveaway_text: str = "", youtube_schedule_path=None, max_publishes: int = 10,
):
    """
    Publica como Reel cada elemento de `schedule` cuya fecha programada
    ya haya pasado y que todavía no se haya publicado -- se sube
    temporalmente a R2 para conseguir la URL pública que exige Instagram,
    se publica, y se borra de R2 en cuanto Instagram ya lo tiene
    descargado. Guarda el progreso tras cada publicación, así que se
    puede relanzar cualquier día sin duplicar nada.

    `giveaway_text`: igual que en upload_lp_schedule, bases de un sorteo
    que se añaden al pie de foto -- como aquí no hay "subida" previa que
    ya quedara fijada, se añade siempre en el momento de publicar (nunca
    queda desactualizado para lo que todavía no se ha publicado).

    `youtube_schedule_path`: ruta a calendario_youtube.json de este mismo
    LP -- si se indica, cada Reel enlaza con el vídeo completo de su tema
    en YouTube ("Escucha el tema completo"), igual que ya hacen los
    Shorts de YouTube entre sí. Si el vídeo principal de ese tema todavía
    no está subido, se publica sin enlace esta vez (no bloquea nada).
    """
    from src.cloud_storage import upload_public_temp, delete_public_temp
    from src.meta_uploader import publish_instagram_video

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

        duration = _video_duration(video_path)
        if not (MIN_REEL_SECONDS <= duration <= MAX_REEL_SECONDS):
            print(
                f"   Aviso: {Path(video_path).name} dura {duration:.1f}s, fuera del "
                f"rango que admite Reels ({MIN_REEL_SECONDS}-{MAX_REEL_SECONDS}s) -- lo salto."
            )
            item["published"] = True  # no reintentar cada día algo que nunca va a valer
            item["skipped_reason"] = "duracion_fuera_de_rango"
            save_instagram_schedule(schedule, save_path)
            continue

        caption = _compose_caption(
            item["caption_base"], giveaway_text,
            main_links.get(item["track_number"]), MAX_CAPTION_LENGTH,
        )

        print(f"\n-> Publicando en Instagram {Path(video_path).name} (programado para {item['publish_at_local']})...")
        public_url, key = upload_public_temp(video_path)
        try:
            media_id = publish_instagram_video(
                ig_user_id=ig_user_id,
                access_token=access_token,
                video_url=public_url,
                caption=caption,
            )
        except Exception as e:
            delete_public_temp(key)
            if _is_rate_limit_error(e):
                print(f"   Límite de publicaciones de Instagram alcanzado por hoy ({e}) -- paro aquí.")
                break
            print(f"   Aviso: no se pudo publicar {Path(video_path).name} en Instagram ({e}).")
            continue

        delete_public_temp(key)
        item["instagram_media_id"] = media_id
        item["published"] = True
        published_count += 1
        save_instagram_schedule(schedule, save_path)

    total = len(schedule)
    publicados = sum(1 for i in schedule if i.get("published"))
    if publicados < total:
        print(f"\n-> Publicados {publicados}/{total} Shorts en Instagram hasta ahora.")
    else:
        print(f"\n-> Los {total} Shorts de este LP ya están publicados en Instagram.")

    return schedule
