"""
tiktok_uploader.py
Publica un vídeo en TikTok usando la Content Posting API (Direct Post),
autenticado por OAuth2 -- ver src/tiktok_auth.py para la gestión del
token y tools/autorizar_tiktok.py para la autorización inicial (solo hace
falta una vez).

AVISO IMPORTANTE: mientras la app no haya pasado la revisión ("audit") de
TikTok para el scope `video.publish`, todo lo que se publique por esta
API sale forzosamente en modo PRIVADO (SELF_ONLY, solo visible para el
propio dueño de la cuenta) -- es una restricción de TikTok a cualquier
app sin auditar, no algo que dependa de este código.

Flujo de publicación (Direct Post, FILE_UPLOAD):
1. POST /v2/post/publish/video/init/ -- registra la publicación, devuelve
   un `publish_id` y una `upload_url` donde subir el vídeo.
2. PUT a esa `upload_url` con los bytes del vídeo. Esta implementación
   sube en un ÚNICO tramo (los Shorts pesan poco, muy por debajo del
   límite de un tramo de TikTok) -- un vídeo más pesado necesitaría subir
   por partes, no soportado aquí.
3. GET /v2/post/publish/status/fetch/ -- TikTok procesa el vídeo en
   segundo plano; hay que esperar a que termine antes de darlo por
   publicado.
"""

import os
import time

import requests

API_BASE = "https://open.tiktokapis.com/v2"

# Límite de TikTok para subir un vídeo en un solo tramo sin partirlo en
# chunks -- de sobra para cualquier Short (unos pocos MB).
MAX_SINGLE_CHUNK_BYTES = 64 * 1024 * 1024


def refresh_access_token(client_key: str, client_secret: str, refresh_token: str) -> dict:
    """
    Cambia un refresh_token por un access_token nuevo -- el access_token
    de TikTok caduca en pocas horas, así que hay que renovarlo antes de
    cada tanda de publicaciones. Devuelve el JSON completo de la
    respuesta (incluye un refresh_token nuevo: TikTok lo rota en cada
    uso, hay que guardar siempre el más reciente, ver src/tiktok_auth.py).
    """
    resp = requests.post(
        f"{API_BASE}/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def exchange_code_for_token(client_key: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """
    Cambia el código de autorización (de la autorización inicial en el
    navegador, ver tools/autorizar_tiktok.py) por el primer access_token
    y refresh_token -- solo hace falta una vez.
    """
    resp = requests.post(
        f"{API_BASE}/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def publish_video_direct_post(
    access_token: str, video_path: str, caption: str,
    privacy_level: str = "SELF_ONLY",
    poll_interval: float = 5.0, poll_timeout: float = 300.0,
):
    """
    Publica `video_path` en TikTok con `caption` como descripción.
    `privacy_level`: "SELF_ONLY" (privado -- el único que de verdad
    funciona mientras la app no esté auditada, ver aviso del módulo),
    "PUBLIC_TO_EVERYONE" o "MUTUAL_FOLLOW_FRIENDS" una vez auditada la
    app. Devuelve el `publish_id`.
    """
    video_size = os.path.getsize(video_path)
    if video_size > MAX_SINGLE_CHUNK_BYTES:
        raise ValueError(
            f"{video_path} pesa {video_size / 1024 / 1024:.1f} MB, por encima del límite de "
            f"{MAX_SINGLE_CHUNK_BYTES / 1024 / 1024:.0f} MB que soporta esta implementación "
            "(sube en un solo tramo, no divide en chunks)."
        )

    init_resp = requests.post(
        f"{API_BASE}/post/publish/video/init/",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={
            "post_info": {"title": caption, "privacy_level": privacy_level},
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": video_size,
                "total_chunk_count": 1,
            },
        },
        timeout=30,
    )
    init_resp.raise_for_status()
    init_data = init_resp.json()["data"]
    publish_id = init_data["publish_id"]
    upload_url = init_data["upload_url"]

    with open(video_path, "rb") as f:
        video_bytes = f.read()
    upload_resp = requests.put(
        upload_url,
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
        },
        data=video_bytes,
        timeout=300,
    )
    upload_resp.raise_for_status()

    deadline = time.time() + poll_timeout
    status = None
    while time.time() < deadline:
        status_resp = requests.post(
            f"{API_BASE}/post/publish/status/fetch/",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={"publish_id": publish_id},
            timeout=30,
        )
        status_resp.raise_for_status()
        status = status_resp.json()["data"]["status"]
        if status == "PUBLISH_COMPLETE":
            break
        if status == "FAILED":
            raise RuntimeError(f"TikTok no pudo publicar el vídeo (publish_id {publish_id}).")
        time.sleep(poll_interval)
    else:
        raise TimeoutError(f"TikTok sigue procesando el vídeo tras {poll_timeout}s (publish_id {publish_id}).")

    print(f"Publicado en TikTok: {publish_id}")
    return publish_id
