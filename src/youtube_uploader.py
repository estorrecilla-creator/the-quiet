"""
youtube_uploader.py
Sube vídeos a YouTube como PRIVADO (o no listado) para revisión manual antes
de publicar. Cuando decidáis automatizar la publicación final, solo hay que
cambiar `privacy_status` a "public" o añadir lógica de programación.

REQUIERE configuración previa (una sola vez):
1. Crear proyecto en Google Cloud Console: https://console.cloud.google.com
2. Activar "YouTube Data API v3"
3. Crear credenciales OAuth 2.0 (tipo "Desktop app") y descargar client_secret.json
   -> guardarlo en config/client_secret.json (NO subir a git)
4. La primera ejecución abrirá el navegador para autorizar la cuenta del canal.
   Tras autorizar, se guarda un token en config/token.json para no repetir el
   proceso cada vez.

Esto NO funciona en este entorno sandbox (necesita acceso a accounts.google.com
y a youtube.googleapis.com, no permitidos aquí). Ejecutar en tu PC/servidor.
"""

import os
import pickle

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRET_PATH = "config/client_secret.json"
TOKEN_PATH = "config/token.json"


def _get_authenticated_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
            # host y bind_addr forzados a 127.0.0.1 (no "localhost"): en
            # Windows el navegador a veces resuelve "localhost" como IPv6
            # mientras el servidor local solo escucha en IPv4, y la
            # redirección de Google falla con "conexión rechazada".
            creds = flow.run_local_server(host="127.0.0.1", bind_addr="127.0.0.1", port=0)
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    category_id: str = "10",  # 10 = Music
    privacy_status: str = "private",  # private | unlisted | public
    publish_at: str = None,  # RFC3339 UTC, ej "2026-07-20T17:00:00Z"
    thumbnail_path: str = None,
    default_language: str = None,  # ej "es" o "en"; ayuda a YouTube a
    # mostrar el vídeo a la audiencia/nicho del idioma correcto
):
    """
    Si se pasa `publish_at`, el vídeo se sube oculto y YouTube lo publica
    automáticamente en esa fecha/hora exacta (UTC) sin que haga falta volver
    a tocar nada. YouTube exige que `privacy_status` sea "private" para
    poder programar la publicación, así que se fuerza automáticamente.
    """
    youtube = _get_authenticated_service()

    if publish_at:
        privacy_status = "private"

    status = {
        "privacyStatus": privacy_status,
        "selfDeclaredMadeForKids": False,
    }
    if publish_at:
        status["publishAt"] = publish_at

    snippet = {
        "title": title[:100],
        "description": description,
        "tags": tags,
        "categoryId": category_id,
    }
    if default_language:
        snippet["defaultLanguage"] = default_language
        snippet["defaultAudioLanguage"] = default_language

    body = {"snippet": snippet, "status": status}

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Subiendo... {int(status.progress() * 100)}%")

    video_id = response["id"]

    if thumbnail_path:
        try:
            youtube.thumbnails().set(
                videoId=video_id, media_body=MediaFileUpload(thumbnail_path)
            ).execute()
            print("Miniatura personalizada subida.")
        except Exception as e:
            print(
                f"Aviso: no se pudo subir la miniatura personalizada ({e}). "
                "El vídeo sigue subido bien, solo se queda sin miniatura propia — "
                "lo más habitual es que el canal necesite el teléfono verificado "
                "para esta función (youtube.com/verify)."
            )

    if publish_at:
        print(f"Subido (oculto) y programado para {publish_at}: https://youtube.com/watch?v={video_id}")
    else:
        print(f"Subido como {privacy_status}: https://youtube.com/watch?v={video_id}")
    return video_id


if __name__ == "__main__":
    import sys
    import json

    video_path = sys.argv[1]
    meta_path = sys.argv[2]  # json con title/description/tags_youtube

    with open(meta_path) as f:
        meta = json.load(f)

    upload_video(
        video_path=video_path,
        title=meta["title"],
        description=meta["description"],
        tags=meta.get("tags_youtube", []),
        privacy_status="private",
    )
