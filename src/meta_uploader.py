"""
meta_uploader.py
Publica vídeos en una Página de Facebook y en una cuenta de Instagram
Business/Creator vinculada a ella, usando la Graph API de Meta.

REQUIERE configuración previa (una sola vez, la hace el usuario en
developers.facebook.com):
1. Crear una app en Meta for Developers y pedir revisión de los permisos
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts` e
   `instagram_content_publish` (esto puede tardar días; conviene pedirlo
   cuanto antes aunque no se use todavía).
2. Vincular la cuenta de Instagram (Business/Creator) a la Página de
   Facebook desde la configuración de la Página.
3. Generar un token de acceso de la Página de larga duración (no caduca a
   los 60 días como el de usuario) desde el Graph API Explorer o el flujo
   de intercambio de token. Guardarlo donde lo lea este módulo (variables
   de entorno PAGE_ACCESS_TOKEN / PAGE_ID / IG_USER_ID en .env).

Diferencias importantes con YouTube:
- Facebook SÍ soporta programar la publicación (scheduled_publish_time):
  se sube el vídeo ya y Meta lo publica solo en la fecha indicada.
- Instagram NO soporta programación nativa vía API: hay que llamar a
  publish_instagram_video() en el momento exacto en que quieres que se
  publique (con el Programador de tareas de Windows, por ejemplo).
- Instagram exige que el vídeo esté accesible por una URL pública en el
  momento de crear el contenedor (no admite subida directa de archivo
  local como YouTube o Facebook) — hay que alojarlo en algún sitio
  público (aunque sea temporalmente) antes de llamar a esta función.
"""

import time

import requests

GRAPH_VERSION = "v19.0"
GRAPH_VIDEO_URL = f"https://graph-video.facebook.com/{GRAPH_VERSION}"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


def create_facebook_video_post(
    page_id: str,
    page_access_token: str,
    video_path: str,
    description: str,
    scheduled_publish_time: int = None,
):
    """
    Sube un vídeo a una Página de Facebook. Si se pasa
    `scheduled_publish_time` (timestamp Unix en UTC), el vídeo se sube
    oculto y Facebook lo publica solo en esa fecha/hora exacta.
    Devuelve el id del vídeo/post creado.
    """
    params = {"description": description, "access_token": page_access_token}
    if scheduled_publish_time is not None:
        params["published"] = "false"
        params["scheduled_publish_time"] = str(scheduled_publish_time)

    with open(video_path, "rb") as f:
        response = requests.post(
            f"{GRAPH_VIDEO_URL}/{page_id}/videos",
            data=params,
            files={"source": f},
            timeout=600,
        )
    response.raise_for_status()
    result = response.json()
    print(f"Vídeo de Facebook creado: {result}")
    return result["id"]


def publish_instagram_video(
    ig_user_id: str,
    access_token: str,
    video_url: str,
    caption: str,
    media_type: str = "REELS",
    poll_interval: float = 5.0,
    poll_timeout: float = 300.0,
):
    """
    Publica un Reel/vídeo en Instagram a partir de una URL pública del
    archivo (Instagram lo descarga desde ahí, no acepta subida directa de
    un archivo local). Se publica de inmediato al llamar a esta función —
    no hay forma de "programarlo" vía API, así que si quieres que salga en
    una fecha concreta, esta función debe ejecutarse justo en ese momento.
    Devuelve el id de la publicación.
    """
    create_resp = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media",
        data={
            "video_url": video_url,
            "caption": caption,
            "media_type": media_type,
            "access_token": access_token,
        },
        timeout=60,
    )
    create_resp.raise_for_status()
    container_id = create_resp.json()["id"]

    # Instagram procesa el vídeo en segundo plano; hay que esperar a que
    # el contenedor esté listo antes de poder publicarlo.
    deadline = time.time() + poll_timeout
    status_code = None
    while time.time() < deadline:
        status_resp = requests.get(
            f"{GRAPH_URL}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=30,
        )
        status_resp.raise_for_status()
        status_code = status_resp.json().get("status_code")
        if status_code == "FINISHED":
            break
        if status_code == "ERROR":
            raise RuntimeError(f"Instagram no pudo procesar el vídeo (contenedor {container_id}).")
        time.sleep(poll_interval)
    else:
        raise TimeoutError(
            f"Instagram sigue procesando el vídeo tras {poll_timeout}s (contenedor {container_id})."
        )

    publish_resp = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=60,
    )
    publish_resp.raise_for_status()
    result = publish_resp.json()
    print(f"Publicado en Instagram: {result}")
    return result["id"]


if __name__ == "__main__":
    import os
    import sys

    from dotenv import load_dotenv
    load_dotenv()

    platform = sys.argv[1]  # "facebook" o "instagram"
    video_arg = sys.argv[2]  # ruta local (facebook) o URL pública (instagram)
    caption = sys.argv[3]

    if platform == "facebook":
        create_facebook_video_post(
            page_id=os.environ["PAGE_ID"],
            page_access_token=os.environ["PAGE_ACCESS_TOKEN"],
            video_path=video_arg,
            description=caption,
        )
    elif platform == "instagram":
        publish_instagram_video(
            ig_user_id=os.environ["IG_USER_ID"],
            access_token=os.environ["PAGE_ACCESS_TOKEN"],
            video_url=video_arg,
            caption=caption,
        )
    else:
        print("Uso: python -m src.meta_uploader facebook|instagram <video> <caption>")
        sys.exit(1)
