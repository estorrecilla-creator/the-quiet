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
import re

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube",  # subida, listas de reproducción, canal...
    "https://www.googleapis.com/auth/youtube.force-ssl",  # comentarios (los
    # comentarios exigen este permiso en concreto, "youtube" solo no basta)
]
# (si vienes de una versión anterior con menos permisos concedidos, borra
# config/token.json para volver a autorizar con el permiso ampliado —
# se abre el navegador un momento, como la primera vez)
CLIENT_SECRET_PATH = "config/client_secret.json"
TOKEN_PATH = "config/token.json"


def _token_path_for(channel: str = None) -> str:
    """
    Un mismo Google/correo puede tener varios canales de YouTube distintos
    detrás (páginas/marca "Brand Account" separadas, ej. IWT y Telvorn con
    el mismo correo) -- cada uno necesita su PROPIO token, porque el token
    guarda a qué canal en concreto se autorizó el acceso, no solo a qué
    correo. `channel=None` (o "default") usa el token de siempre
    (config/token.json, sin renombrar nada de lo que ya funcionaba); un
    nombre de canal nuevo usa config/token_<nombre>.json -- si ese archivo
    no existe todavía, la primera vez se abre el navegador y hay que
    elegir ahí, a mano, la página/canal correcta (Google lo pregunta
    cuando la cuenta tiene más de un canal vinculado).
    """
    if not channel or str(channel).strip().lower() in ("", "default"):
        return TOKEN_PATH
    slug = re.sub(r"[^a-z0-9_-]+", "_", str(channel).strip().lower()).strip("_") or "default"
    return f"config/token_{slug}.json"


def get_authenticated_service(channel: str = None):
    return _get_authenticated_service(channel)


def _get_authenticated_service(channel: str = None):
    token_path = _token_path_for(channel)
    creds = None
    if os.path.exists(token_path):
        with open(token_path, "rb") as f:
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
        os.makedirs(os.path.dirname(token_path) or ".", exist_ok=True)
        with open(token_path, "wb") as f:
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
    channel: str = None,  # a qué canal subir, si el correo tiene varios (ver _token_path_for)
):
    """
    Si se pasa `publish_at`, el vídeo se sube oculto y YouTube lo publica
    automáticamente en esa fecha/hora exacta (UTC) sin que haga falta volver
    a tocar nada. YouTube exige que `privacy_status` sea "private" para
    poder programar la publicación, así que se fuerza automáticamente.
    """
    youtube = _get_authenticated_service(channel)

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


def update_video_schedule(video_id: str, publish_at: str, channel: str = None):
    """
    Cambia la fecha/hora de publicación programada de un vídeo YA SUBIDO
    (sigue privado hasta esa fecha) -- para adelantar/atrasar el
    calendario de un LP que ya se subió a YouTube sin tener que volver a
    subir nada. YouTube exige `privacyStatus: "private"` para poder fijar
    `publishAt` (igual que en la subida inicial en upload_video)."""
    youtube = _get_authenticated_service(channel)
    youtube.videos().update(
        part="status",
        body={"id": video_id, "status": {"privacyStatus": "private", "publishAt": publish_at}},
    ).execute()


def update_video_description(video_id: str, description: str, channel: str = None):
    """
    Cambia la descripción de un vídeo ya subido, sin tocar el resto de
    metadatos. YouTube exige mandar el "snippet" completo en cada
    actualización (no solo el campo que cambia), así que primero se lee
    el snippet actual y solo se sustituye la descripción.
    """
    youtube = _get_authenticated_service(channel)
    current = youtube.videos().list(part="snippet", id=video_id).execute()
    items = current.get("items", [])
    if not items:
        return
    snippet = items[0]["snippet"]
    snippet["description"] = description
    youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()


def append_to_video_description(video_id: str, extra_text: str, marker: str = None, channel: str = None):
    """
    Añade `extra_text` al FINAL de la descripción actual de un vídeo ya
    subido, sin tocar lo que ya había por delante (por ejemplo, los
    enlaces "escucha el tema completo"/"sigue escuchando" que ya
    llevaban). Si `marker` ya aparece en la descripción actual, se
    SUSTITUYE ese bloque anterior (desde el marcador hasta el final) por
    el nuevo, en vez de dejarlo tal cual — así se puede relanzar para
    corregir un enlace equivocado o añadir una plataforma nueva más
    adelante, sin que el bloque viejo se quede pegado para siempre.
    """
    youtube = _get_authenticated_service(channel)
    current = youtube.videos().list(part="snippet", id=video_id).execute()
    items = current.get("items", [])
    if not items:
        return
    snippet = items[0]["snippet"]
    description = snippet.get("description", "")
    if marker and marker in description:
        description = description[: description.index(marker)].rstrip()
    new_description = f"{description}\n\n{extra_text}" if description else extra_text
    snippet["description"] = new_description
    youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()


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
