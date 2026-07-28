"""
bluesky_uploader.py
Publica un vídeo en Bluesky (protocolo AT) usando una "contraseña de
aplicación" -- a diferencia de Meta, Bluesky no exige ninguna revisión de
app ni vinculación con otra cuenta: basta con generar esa contraseña
desde la propia cuenta (Configuración -> Contraseñas de aplicaciones) y
usarla aquí, nunca la contraseña normal de la cuenta.

Flujo de publicación (documentado en atproto.com / docs.bsky.app):
1. com.atproto.server.createSession -- autentica y da un token
   (accessJwt) y el DID (identificador único) de la cuenta.
2. com.atproto.repo.uploadBlob -- sube el vídeo en sí (bytes en bruto),
   devuelve una referencia ("blob") al archivo ya alojado por Bluesky.
   A diferencia de Instagram, NO hace falta ninguna URL pública propia
   (ver src/meta_uploader.py) -- Bluesky acepta el archivo directamente.
3. com.atproto.repo.createRecord -- crea la publicación de verdad,
   enlazando ese blob como embed de tipo "app.bsky.embed.video".

Límites (2026): vídeo hasta 100 MB / 3 minutos, MP4; texto hasta 300
"grafemas" (se trunca de forma conservadora por caracteres en
src/bluesky_schedule.py).
"""

from datetime import datetime, timezone

import requests

API_BASE = "https://bsky.social/xrpc"


def _create_session(handle: str, app_password: str):
    resp = requests.post(
        f"{API_BASE}/com.atproto.server.createSession",
        json={"identifier": handle, "password": app_password},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["accessJwt"], data["did"]


def _upload_video_blob(access_jwt: str, video_path: str):
    with open(video_path, "rb") as f:
        video_bytes = f.read()
    resp = requests.post(
        f"{API_BASE}/com.atproto.repo.uploadBlob",
        headers={
            "Authorization": f"Bearer {access_jwt}",
            "Content-Type": "video/mp4",
        },
        data=video_bytes,
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json()["blob"]


def publish_video_post(
    handle: str, app_password: str, video_path: str, text: str,
    aspect_ratio: dict = None,
):
    """
    Publica `video_path` como una publicación de Bluesky con `text` como
    texto del post. `aspect_ratio`: {"width":.., "height":..} opcional --
    evita que un vídeo vertical salga con bandas negras en algunos
    clientes; si no se sabe, mejor omitirlo que adivinarlo. Devuelve el
    "uri" de la publicación creada.
    """
    access_jwt, did = _create_session(handle, app_password)
    blob = _upload_video_blob(access_jwt, video_path)

    embed = {"$type": "app.bsky.embed.video", "video": blob}
    if aspect_ratio:
        embed["aspectRatio"] = aspect_ratio

    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "embed": embed,
    }
    resp = requests.post(
        f"{API_BASE}/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {access_jwt}"},
        json={"repo": did, "collection": "app.bsky.feed.post", "record": record},
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()
    print(f"Publicado en Bluesky: {result}")
    return result["uri"]


if __name__ == "__main__":
    import os
    import sys

    from dotenv import load_dotenv
    load_dotenv()

    video_path = sys.argv[1]
    text = sys.argv[2]
    publish_video_post(
        handle=os.environ["BLUESKY_HANDLE"],
        app_password=os.environ["BLUESKY_APP_PASSWORD"],
        video_path=video_path,
        text=text,
    )
