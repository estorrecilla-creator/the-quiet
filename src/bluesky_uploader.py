"""
bluesky_uploader.py
Publica un vídeo en Bluesky (protocolo AT) usando una "contraseña de
aplicación" -- a diferencia de Meta, Bluesky no exige ninguna revisión de
app ni vinculación con otra cuenta: basta con generar esa contraseña
desde la propia cuenta (Configuración -> Contraseñas de aplicaciones) y
usarla aquí, nunca la contraseña normal de la cuenta.

Flujo de publicación de VÍDEO (docs.bsky.app/docs/tutorials/video):
1. com.atproto.server.createSession -- autentica y da un token
   (accessJwt) y el DID (identificador único) de la cuenta.
2. com.atproto.server.getServiceAuth -- pide un token de servicio aparte
   (no el accessJwt de sesión) con permiso ("lxm") justo para
   com.atproto.repo.uploadBlob y destino ("aud") el PDS de la cuenta --
   video.bsky.app lo necesita para poder subir el blob final a tu
   repositorio en tu nombre, una vez procesado.
3. app.bsky.video.uploadVideo (en video.bsky.app, NO en bsky.social) --
   sube el vídeo en bruto y arranca un trabajo de procesado/
   transcodificado ASÍNCRONO (a HLS, para que se pueda reproducir en
   cualquier conexión). Devuelve un jobId, no un blob usable todavía.
4. app.bsky.video.getJobStatus -- se sondea en bucle hasta que el
   trabajo termina (state "JOB_STATE_COMPLETED", con el blob YA
   procesado) o falla (state "JOB_STATE_FAILED").
5. com.atproto.repo.createRecord -- crea la publicación de verdad,
   enlazando ESE blob (el devuelto por el trabajo ya terminado) como
   embed de tipo "app.bsky.embed.video".

AVISO 1 -- error real detectado en producción (el Short no se veía en
Bluesky): la primera versión de este módulo subía el vídeo directamente
con com.atproto.repo.uploadBlob (igual que se haría con una imagen) y
usaba ese blob tal cual en el embed, saltándose los pasos 2-4. La llamada
a la API no falla (el post se crea sin error, "Publicado en Bluesky" se
imprime igual), pero el blob nunca pasa por el pipeline de transcodificado
de vídeo que la app/web de Bluesky necesita para reproducirlo -- el
resultado es un post real con el hueco del vídeo vacío/roto. Es un fallo
ya documentado por el propio equipo de Bluesky para quien comete el mismo
error (GitHub bluesky-social/atproto discussion #3899, "Record Not Found"
donde debería verse el vídeo). El único camino soportado es el de arriba.

AVISO 2 -- segundo error real detectado al arreglar el primero: el "aud"
que exige getServiceAuth (paso 2) tiene que ser el DID del PDS que aloja
DE VERDAD la cuenta, no "bsky.social" -- ese dominio es solo la puerta de
entrada/API pública; la inmensa mayoría de cuentas (incluida la nuestra)
viven en un shard propio (ej. "chalciporus.us-west.host.bsky.network").
Pedir el token con el aud equivocado (bsky.social a pelo) lo rechaza
video.bsky.app con 401 Unauthorized. El PDS real de la cuenta ya viene en
la propia respuesta de createSession (didDoc.service, id "#atproto_pds"),
así que se lee de ahí en vez de asumir nada.

Límites (2026): vídeo hasta 100 MB / 3 minutos, MP4; texto hasta 300
"grafemas" (se trunca de forma conservadora por caracteres en
src/bluesky_schedule.py).
"""

import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

API_BASE = "https://bsky.social/xrpc"
VIDEO_API_BASE = "https://video.bsky.app/xrpc"

# Cuánto se espera a que Bluesky termine de procesar/transcodificar el
# vídeo antes de rendirse -- de sobra para un Short de ~20-35s (en la
# práctica tarda bastante menos), sin quedarse esperando indefinidamente
# si el servicio de vídeo tiene un problema real ese día.
JOB_POLL_INTERVAL_SECONDS = 3
JOB_POLL_TIMEOUT_SECONDS = 180


def _create_session(handle: str, app_password: str):
    resp = requests.post(
        f"{API_BASE}/com.atproto.server.createSession",
        json={"identifier": handle, "password": app_password},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["accessJwt"], data["did"], _pds_did_from_session(data)


def _pds_did_from_session(session_data: dict) -> str:
    """
    El DID del PDS real de la cuenta (ver AVISO 2 arriba), a partir del
    didDoc que ya devuelve createSession -- sin necesidad de otra llamada
    aparte para resolverlo.
    """
    services = (session_data.get("didDoc") or {}).get("service", [])
    pds = next((s for s in services if s.get("id") == "#atproto_pds"), None)
    if not pds:
        raise RuntimeError(
            "No se pudo determinar el PDS real de la cuenta (falta "
            "didDoc.service en la respuesta de createSession de Bluesky)."
        )
    hostname = urlparse(pds["serviceEndpoint"]).hostname
    return f"did:web:{hostname}"


def _get_video_service_token(access_jwt: str, pds_did: str) -> str:
    """
    Token de servicio (distinto del accessJwt de sesión) que exige
    video.bsky.app para poder subir el blob final a tu repositorio en tu
    nombre, una vez procesado el vídeo. `pds_did`: el DID del PDS real de
    la cuenta (ver AVISO 2), nunca un valor fijo.
    """
    resp = requests.get(
        f"{API_BASE}/com.atproto.server.getServiceAuth",
        params={
            "aud": pds_did,
            "lxm": "com.atproto.repo.uploadBlob",
            "exp": int(time.time()) + 60 * 30,  # 30 min de margen
        },
        headers={"Authorization": f"Bearer {access_jwt}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["token"]


def _upload_video_and_wait_for_processing(did: str, service_token: str, video_path: str):
    """
    Sube el vídeo al SERVICIO DE VÍDEO (arranca el trabajo de
    transcodificado asíncrono) y espera a que termine. El blob que
    devuelve el trabajo ya completado es el único válido para el embed
    -- ver el aviso en la cabecera del archivo sobre por qué un blob
    subido a pelo con uploadBlob nunca llega a reproducirse.
    """
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    resp = requests.post(
        f"{VIDEO_API_BASE}/app.bsky.video.uploadVideo",
        params={"did": did, "name": Path(video_path).name},
        headers={
            "Authorization": f"Bearer {service_token}",
            "Content-Type": "video/mp4",
            "Content-Length": str(len(video_bytes)),
        },
        data=video_bytes,
        timeout=300,
    )
    resp.raise_for_status()
    job = resp.json()

    if job.get("blob"):
        return job["blob"]  # ya vino procesado en la propia respuesta

    job_id = job["jobId"]
    deadline = time.monotonic() + JOB_POLL_TIMEOUT_SECONDS
    while True:
        time.sleep(JOB_POLL_INTERVAL_SECONDS)
        status_resp = requests.get(
            f"{VIDEO_API_BASE}/app.bsky.video.getJobStatus",
            params={"jobId": job_id},
            timeout=30,
        )
        status_resp.raise_for_status()
        job_status = status_resp.json()["jobStatus"]

        if job_status["state"] == "JOB_STATE_COMPLETED":
            return job_status["blob"]
        if job_status["state"] == "JOB_STATE_FAILED":
            raise RuntimeError(
                f"Bluesky no pudo procesar el vídeo (jobId={job_id}): "
                f"{job_status.get('error', 'sin detalle')} -- {job_status.get('message', '')}"
            )
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Bluesky sigue procesando el vídeo tras {JOB_POLL_TIMEOUT_SECONDS}s "
                f"(jobId={job_id}, estado {job_status['state']}) -- probablemente "
                "termine más tarde, pero no se puede publicar el post todavía sin "
                "el blob ya procesado."
            )


def publish_video_post(
    handle: str, app_password: str, video_path: str, text: str,
    aspect_ratio: dict = None, facets: list = None,
):
    """
    Publica `video_path` como una publicación de Bluesky con `text` como
    texto del post. `aspect_ratio`: {"width":.., "height":..} opcional --
    evita que un vídeo vertical salga con bandas negras en algunos
    clientes; si no se sabe, mejor omitirlo que adivinarlo. `facets`:
    lista de enlaces "de verdad" dentro del texto (Bluesky no admite
    markdown tipo [texto](url) -- un facet marca un tramo del propio
    `text`, por posición en BYTES de su codificación UTF-8, y lo
    convierte en un enlace clicable a otra URL sin cambiar lo que se ve
    escrito). Devuelve el "uri" de la publicación creada.
    """
    access_jwt, did, pds_did = _create_session(handle, app_password)
    service_token = _get_video_service_token(access_jwt, pds_did)
    blob = _upload_video_and_wait_for_processing(did, service_token, video_path)

    embed = {"$type": "app.bsky.embed.video", "video": blob}
    if aspect_ratio:
        embed["aspectRatio"] = aspect_ratio

    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "embed": embed,
    }
    if facets:
        record["facets"] = facets
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
