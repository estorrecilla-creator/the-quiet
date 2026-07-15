"""
stock_video.py
Busca y descarga clips de vídeo libres de derechos (uso comercial
permitido, sin atribución obligatoria) en Pexels, Pixabay y Coverr, como
alternativa gratuita a generar vídeo con IA de pago. Prueba las fuentes en
orden y se queda con el primer clip válido — entre las tres hay más
posibilidades de encontrar uno que encaje para cada búsqueda. Si ninguna
encuentra nada, devuelve None para que el que llama pueda usar una imagen
generada por IA como respaldo en su lugar.

Requiere una clave gratuita de Pexels y/o Pixabay (sin coste, aprobación
instantánea) y/o Coverr (gratis, pero hay que pedirla por email):
https://www.pexels.com/api/
https://pixabay.com/api/docs/
https://api.coverr.co/docs/start/
"""

import os
import subprocess

import requests

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PIXABAY_SEARCH_URL = "https://pixabay.com/api/videos/"
COVERR_SEARCH_URL = "https://api.coverr.co/videos"

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
    exclude_urls: set = None,
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
    `exclude_urls`: URLs ya usadas antes en el mismo LP (para no repetir
    el mismo clip en ningún tema ni dentro del mismo tema) — se saltan.
    Devuelve la URL del archivo cuyo lado largo esté más cerca de 1920
    entre los que sí cumplen la calidad mínima, o None si no hay ningún
    resultado válido nuevo.
    """
    exclude_urls = exclude_urls or set()
    response = requests.get(
        PEXELS_SEARCH_URL,
        headers={"Authorization": api_key},
        params={"query": query, "orientation": orientation, "per_page": 15},
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
        if chosen["link"] in exclude_urls:
            continue
        return chosen["link"]

    return None


def search_pixabay_clip(
    query: str,
    api_key: str,
    min_duration: float = 4.0,
    orientation: str = "landscape",
    min_short_side: int = 720,
    exclude_urls: set = None,
):
    """
    Igual que `search_pexels_clip` pero contra la API de Pixabay. Pixabay
    no tiene parámetro de orientación en la búsqueda de vídeo (a
    diferencia de Pexels), así que la orientación se comprueba a mano
    sobre las dimensiones reales de cada variante descargable. Los tags
    de cada vídeo (en vez del slug de la URL) son los que se comprueban
    contra BANNED_TERMS. `exclude_urls`: ver `search_pexels_clip`.
    """
    exclude_urls = exclude_urls or set()
    response = requests.get(
        PIXABAY_SEARCH_URL,
        params={"key": api_key, "q": query, "per_page": 15, "safesearch": "true"},
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
        if chosen["url"] in exclude_urls:
            continue
        return chosen["url"]

    return None


def search_coverr_clip(
    query: str,
    api_key: str,
    min_duration: float = 4.0,
    orientation: str = "landscape",
    min_short_side: int = 720,
    exclude_urls: set = None,
):
    """
    Igual que las anteriores pero contra la API de Coverr. Coverr sí
    indica la orientación directamente (`is_vertical`), y solo ofrece una
    URL de descarga por vídeo (no varias calidades a elegir), así que la
    comprobación de calidad mínima es sobre esa única variante. El título,
    la descripción y los tags son los que se comprueban contra
    BANNED_TERMS. `exclude_urls`: ver `search_pexels_clip`.
    """
    exclude_urls = exclude_urls or set()
    response = requests.get(
        COVERR_SEARCH_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        params={"query": query, "page_size": 15, "urls": "true"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    wants_vertical = orientation != "landscape"
    for hit in data.get("hits", []):
        if hit.get("duration", 0) < min_duration:
            continue
        if bool(hit.get("is_vertical")) != wants_vertical:
            continue
        description = " ".join(
            str(hit.get(field, "")) for field in ("title", "description")
        ) + " " + " ".join(hit.get("tags") or [])
        if _contains_banned_term(description):
            continue
        if min(hit.get("max_width") or 0, hit.get("max_height") or 0) < min_short_side:
            continue
        url = (hit.get("urls") or {}).get("mp4")
        if url and url not in exclude_urls:
            return url

    return None


def download_video(url: str, out_path: str) -> str:
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    return out_path


def _is_valid_video(path: str, min_duration: float = 1.0) -> bool:
    """
    Comprueba con ffprobe que el archivo descargado es un vídeo de verdad
    (no un HTML de error, ni un archivo cortado a mitad de descarga por
    un corte de red) y que tiene al menos `min_duration` segundos. Sin
    esto, un archivo corrupto puede colarse hasta el render final y fallar
    ahí con un error de ffmpeg mucho más difícil de diagnosticar.
    """
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return False
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return False
    return duration >= min_duration


def find_stock_clip(
    query: str,
    out_path: str,
    api_key: str = None,
    min_duration: float = 4.0,
    orientation: str = "landscape",
    min_short_side: int = 720,
    pixabay_api_key: str = None,
    coverr_api_key: str = None,
    exclude_urls: set = None,
):
    """
    Busca y descarga en un solo paso. Prueba Pexels, luego Pixabay, luego
    Coverr (cada una solo si tiene clave configurada), y se queda con el
    primer clip válido — más posibilidades de encontrar uno que encaje
    entre las tres. Si no encuentra nada o falla en todas, devuelve None
    (no lanza excepción) para poder usar una imagen de IA como respaldo
    sin interrumpir el resto del proceso.

    `exclude_urls`: set mutable con las URLs ya usadas antes (en el mismo
    tema o en otros temas del mismo LP) — se descartan como candidatas, y
    si esta búsqueda encuentra una válida nueva, se añade sola a este
    mismo set antes de devolver, para que la siguiente llamada ya la vea
    como usada (así nunca se repite el mismo clip en todo el LP).
    """
    pexels_key = api_key or os.environ.get("PEXELS_API_KEY")
    pixabay_key = pixabay_api_key or os.environ.get("PIXABAY_API_KEY")
    coverr_key = coverr_api_key or os.environ.get("COVERR_API_KEY")

    for key, search_fn in (
        (pexels_key, search_pexels_clip),
        (pixabay_key, search_pixabay_clip),
        (coverr_key, search_coverr_clip),
    ):
        if not key:
            continue
        try:
            url = search_fn(
                query, key, min_duration=min_duration,
                orientation=orientation, min_short_side=min_short_side,
                exclude_urls=exclude_urls,
            )
        except requests.RequestException:
            continue
        if not url:
            continue
        try:
            download_video(url, out_path)
        except requests.RequestException:
            continue
        if _is_valid_video(out_path, min_duration=min_duration):
            if exclude_urls is not None:
                exclude_urls.add(url)
            return out_path
        # descarga corrupta/incompleta (corte de red a mitad, HTML de
        # error guardado como si fuera vídeo...): la descartamos y
        # probamos con la siguiente fuente en vez de devolver un archivo
        # roto que reventaría más adelante en el render.
        if os.path.exists(out_path):
            os.remove(out_path)

    return None
