"""
cloud_storage.py
Sube un archivo temporalmente a un almacenamiento con lectura pública
(Cloudflare R2, compatible con S3) para conseguir una URL pública que
otras APIs puedan usar para descargarlo -- Instagram, a diferencia de
YouTube, no acepta subida directa de un archivo local: exige una URL
pública desde la que descargarlo él mismo (ver publish_instagram_video en
src/meta_uploader.py).

REQUIERE una cuenta gratuita de Cloudflare R2 (10 GB gratis, sin coste
por tráfico de salida) con:
1. Un bucket con acceso público activado (Configuración del bucket ->
   "R2.dev subdomain" -> Allow Access) -- da una URL pública del tipo
   https://pub-XXXX.r2.dev/archivo.mp4
2. Un token de API (R2 -> "Manage API tokens" -> Create API token, con
   permiso de lectura y escritura sobre ese bucket).

Variables de entorno necesarias (.env):
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
    R2_BUCKET_NAME, R2_PUBLIC_BASE_URL (la URL pub-XXXX.r2.dev de arriba,
    sin barra final)
"""

import os
import uuid
from pathlib import Path


def _client():
    import boto3
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def upload_public_temp(file_path: str):
    """
    Sube `file_path` al bucket y devuelve (url_publica, key) -- guarda
    `key` para poder borrarlo luego con delete_public_temp() en cuanto
    Instagram ya lo haya descargado y publicado.
    """
    bucket = os.environ["R2_BUCKET_NAME"]
    base_url = os.environ["R2_PUBLIC_BASE_URL"].rstrip("/")
    key = f"instagram-tmp/{uuid.uuid4().hex}{Path(file_path).suffix}"
    _client().upload_file(file_path, bucket, key, ExtraArgs={"ContentType": "video/mp4"})
    return f"{base_url}/{key}", key


def delete_public_temp(key: str):
    bucket = os.environ["R2_BUCKET_NAME"]
    _client().delete_object(Bucket=bucket, Key=key)
