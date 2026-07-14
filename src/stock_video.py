"""
stock_video.py
Busca y descarga clips de vídeo libres de derechos (uso comercial
permitido, sin atribución obligatoria) en Pexels y Pixabay, como
alternativa gratuita a generar vídeo con IA de pago. Prueba primero
Pexels y, si no hay clave o no encuentra nada que encaje, cae en Pixabay
— entre las dos fuentes hay más posibilidades de encontrar un clip válido
para cada búsqueda. Si ninguna de las dos encuentra nada, devuelve None
para que el que llama pueda usar una imagen generada por IA como respaldo
en su lugar.

Requiere una clave gratuita de Pexels y/o Pixabay (sin coste, aprobación
instantánea):
https://www.pexels.com/api/
https://pixabay.com/api/docs/
"""

import os

import requests

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PIXABAY_SEARCH_URL = "https://pixabay.com/api/videos/"

# Si la descripción del vídeo (slug de Pexels, tags de Pixabay) contiene
# alguna de estas palabras, lo descartamos aunque la búsqueda lo haya
# devuelto: la petición es explícita — sin caras reconocibles ni miradas
# a cámara en primer plano.
BANNED_TERMS = (
    "face", "faces", "portrait", "close-up", "closeup", "selfie",
    "headshot", "head-shot", "eye-contact", "looking-at-camera",
    "smiling", "smile", "makeup", "make-up",
)


def _contains_banned_term(text: str) -> bool:
    text = (text or "").lower()
    return any(term in text for term in BANNED_TERMS)


def search_pexels_clip(
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
    También se descartan vídeos cuyo propio título/slug en Pexels sugiera
    una cara en primer plano o mirando a cámara (ver BANNED_TERMS): si
    aparece una persona debe ser de espaldas, de lejos o en silueta.
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
        if _contains_banned_term(video.get("url")):
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


def search_pixabay_clip(
    query: str,
    api_key: str,
    min_duration: float = 4.0,
    orientation: str = "landscape",
    min_short_side: int = 720,
):
    """
    Igual que `search_pexels_clip` pero contra la API de Pixabay. Pixabay
    no tiene parámetro de orientación en la búsqueda de vídeo (a
    diferencia de Pexels), así que la orientación se comprueba a mano
    sobre las dimensiones reales de cada variante descargable. Los tags
    de cada vídeo (en vez del slug de la URL) son los que se comprueban
    contra BANNED_TERMS.
    """
    response = requests.get(
        PIXABAY_SEARCH_URL,
        params={"key": api_key, "q": query, "per_page": 5, "safesearch": "true"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    wants_landscape = orientation == "landscape"
    for hit in data.get("hits", []):
        if hit.get("duration", 0) < min_duration:
            continue
        if _contains_banned_term(hit.get("tags")):
            continue
        variants = [
            v for v in hit.get("videos", {}).values()
            if isinstance(v, dict) and v.get("url") and v.get("width") and v.get("height")
        ]
        hd_variants = [
            v for v in variants
            if min(v["width"], v["height"]) >= min_short_side
            and (v["width"] >= v["height"]) == wants_landscape
        ]
        if not hd_variants:
            continue
        chosen = min(hd_variants, key=lambda v: abs(max(v["width"], v["height"]) - 1920))
        return chosen["url"]

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
    pixabay_api_key: str = None,
):
    """
    Busca y descarga en un solo paso. Prueba primero Pexels y, si no hay
    clave configurada o no encuentra nada que encaje, cae en Pixabay
    (misma clave-o-None por variable de entorno). Si no encuentra nada o
    falla en ambas fuentes, devuelve None (no lanza excepción) para poder
    usar una imagen de IA como respaldo sin interrumpir el resto del
    proceso.
    """
    pexels_key = api_key or os.environ.get("PEXELS_API_KEY")
    pixabay_key = pixabay_api_key or os.environ.get("PIXABAY_API_KEY")

    for key, search_fn in (
        (pexels_key, search_pexels_clip),
        (pixabay_key, search_pixabay_clip),
    ):
        if not key:
            continue
        try:
            url = search_fn(
                query, key, min_duration=min_duration,
                orientation=orientation, min_short_side=min_short_side,
            )
        except requests.RequestException:
            continue
        if url:
            try:
                return download_video(url, out_path)
            except requests.RequestException:
                continue

    return None
