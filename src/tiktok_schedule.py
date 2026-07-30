"""
tiktok_schedule.py
Publica en TikTok los mismos Shorts que ya se suben a YouTube, en el
mismo orden y con las mismas fechas -- mismo patrón exacto que
src/instagram_schedule.py y src/bluesky_schedule.py.

AVISO IMPORTANTE (ver también src/tiktok_uploader.py): mientras la app de
TikTok no haya pasado la revisión ("audit") del scope `video.publish`,
todo lo publicado aquí sale forzosamente en modo PRIVADO (SELF_ONLY, solo
visible para el propio dueño de la cuenta) -- no es un fallo de este
script, es una restricción de TikTok a cualquier app sin auditar.

Como Instagram y Bluesky, TikTok tampoco admite programar la publicación
vía API: solo se publican los elementos cuya fecha ya haya pasado --
pensado para relanzarse a diario, como continuar_subida_youtube.py.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MAX_CAPTION_LENGTH = 2200
MIN_VIDEO_SECONDS = 3
MAX_VIDEO_SECONDS = 600

_CARRY_OVER_FIELDS = ("published", "tiktok_publish_id", "skipped_reason")


def build_tiktok_schedule_from_youtube(youtube_schedule_path, existing_schedule=None) -> list:
    """
    Crea (o actualiza) el calendario de TikTok a partir del de YouTube --
    mismas fechas, mismo orden, solo los Shorts. Se puede (y debe)
    llamar en cada ejecución, no solo la primera vez: los elementos YA
    publicados conservan su estado (emparejados por `video_path`), y los
    pendientes siempre adoptan la fecha/descripción más reciente de
    YouTube -- así, si el LP se reprograma más adelante
    (tools/reprogramar_lp.py), este calendario se pone al día solo.
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
            "tiktok_publish_id": None,
            "published": False,
        }
        old = existing_by_path.get(item["video_path"])
        if old and old.get("published"):
            entry.update({k: old[k] for k in _CARRY_OVER_FIELDS if k in old})
        schedule.append(entry)
    return schedule


def save_tiktok_schedule(schedule, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)
    return out_path


def load_tiktok_schedule(path):
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


def _is_rate_limit_error(exc) -> bool:
    """
    TikTok devuelve HTTP 429 (o un código de error propio tipo
    "rate_limit_exceeded" en el cuerpo) cuando se supera el límite de
    peticiones -- basta con mirar el código de estado.
    """
    import requests
    return (
        isinstance(exc, requests.exceptions.HTTPError)
        and exc.response is not None
        and exc.response.status_code == 429
    )


def publish_due_tiktok_items(
    schedule, save_path, access_token: str,
    giveaway_text: str = "", max_publishes: int = 10, privacy_level: str = "SELF_ONLY",
):
    """
    Publica cada elemento de `schedule` cuya fecha programada ya haya
    pasado y que todavía no se haya publicado. Guarda el progreso tras
    cada publicación, así que se puede relanzar cualquier día sin
    duplicar nada. `privacy_level`: "SELF_ONLY" mientras la app no esté
    auditada por TikTok (ver aviso del módulo).
    """
    from src.tiktok_uploader import publish_video_direct_post

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
        if not (MIN_VIDEO_SECONDS <= duration <= MAX_VIDEO_SECONDS):
            print(
                f"   Aviso: {Path(video_path).name} dura {duration:.1f}s, fuera del "
                f"rango que admite TikTok ({MIN_VIDEO_SECONDS}-{MAX_VIDEO_SECONDS}s) -- lo salto."
            )
            item["published"] = True
            item["skipped_reason"] = "duracion_fuera_de_rango"
            save_tiktok_schedule(schedule, save_path)
            continue

        caption = item["caption_base"]
        if giveaway_text and giveaway_text.strip():
            caption = f"{caption}\n\n{giveaway_text.strip()}"
        caption = caption[:MAX_CAPTION_LENGTH]

        print(f"\n-> Publicando en TikTok {Path(video_path).name} (programado para {item['publish_at_local']})...")
        try:
            publish_id = publish_video_direct_post(
                access_token, video_path, caption, privacy_level=privacy_level,
            )
        except Exception as e:
            if _is_rate_limit_error(e):
                print(f"   Límite de publicaciones de TikTok alcanzado por hoy ({e}) -- paro aquí.")
                break
            print(f"   Aviso: no se pudo publicar {Path(video_path).name} en TikTok ({e}).")
            continue

        item["tiktok_publish_id"] = publish_id
        item["published"] = True
        published_count += 1
        save_tiktok_schedule(schedule, save_path)

    total = len(schedule)
    publicados = sum(1 for i in schedule if i.get("published"))
    if publicados < total:
        print(f"\n-> Publicados {publicados}/{total} Shorts en TikTok hasta ahora.")
    else:
        print(f"\n-> Los {total} Shorts de este LP ya están publicados en TikTok.")

    return schedule
