"""
stock_video.py
Busca y descarga clips de vídeo libres de derechos (uso comercial
permitido, sin atribución obligatoria) en Pexels, como alternativa
gratuita a generar vídeo con IA de pago. Si no encuentra nada que encaje
bien para una búsqueda, devuelve None para que el que llama pueda usar
una imagen generada por IA como respaldo en su lugar.

Requiere una clave gratuita de Pexels (sin coste, aprobación instantánea):
https://www.pexels.com/api/
"""

import os

import requests

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"


def search_stock_clip(
    query: str,
    api_key: str,
    min_duration: float = 4.0,
    orientation: str = "landscape",
    min_short_side: int = 720,
):
    """
    Busca en Pexels un vídeo que encaje con `query`, orientado según
    `orientation` ("landscape" para el vídeo principal, "portrait" para
    Shorts/Reels). Calidad mínima estricta: si un resultado no tiene
    ningún archivo con el lado corto (el que define la resolución real,
    da igual la orientación) de al menos `min_short_side` píxeles, se
    descarta ese vídeo entero — no cae a una versión de menor calidad.
    Devuelve la URL del archivo cuyo lado largo esté más cerca de 1920
    entre los que sí cumplen la calidad mínima, o None si no hay ningún
    resultado válido.
    """
    response = requests.get(
        PEXELS_SEARCH_URL,
        headers={"Authorization": api_key},
        params={"query": query, "orientation": orientation, "per_page": 5},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    for video in data.get("videos", []):
        if video.get("duration", 0) < min_duration:
            continue
        files = video.get("video_files", [])
        hd_files = [
            f for f in files
            if min((f.get("width") or 0), (f.get("height") or 0)) >= min_short_side
        ]
        if not hd_files:
            continue  # ningún archivo de este vídeo llega a la calidad mínima
        chosen = min(
            hd_files,
            key=lambda f: abs(max((f.get("width") or 0), (f.get("height") or 0)) - 1920),
        )
        return chosen["link"]

    return None


def download_video(url: str, out_path: str) -> str:
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    return out_path


def find_stock_clip(
    query: str,
    out_path: str,
    api_key: str = None,
    min_duration: float = 4.0,
    orientation: str = "landscape",
    min_short_side: int = 720,
):
    """
    Busca y descarga en un solo paso. Si no encuentra nada o falla,
    devuelve None (no lanza excepción) para poder usar una imagen de IA
    como respaldo sin interrumpir el resto del proceso.
    """
    api_key = api_key or os.environ.get("PEXELS_API_KEY")
    if not api_key:
        return None
    try:
        url = search_stock_clip(
            query, api_key, min_duration=min_duration,
            orientation=orientation, min_short_side=min_short_side,
        )
        if not url:
            return None
        return download_video(url, out_path)
    except requests.RequestException:
        return None
