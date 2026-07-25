"""
public_domain_archives.py
Busca imágenes de dominio público / licencia libre en archivos con
metadatos de derechos fiables y consultables por API — pensado para
proyectos que necesitan material histórico real (ej. fotografías,
carteles) en vez de vídeo de stock genérico.

A diferencia de stock_video.py (Pexels/Pixabay/Coverr, donde TODO el
catálogo está pre-autorizado para uso comercial), estos archivos tienen
contenido MIXTO: solo una parte de lo que alojan es reutilizable. Por
eso cada resultado se descarta salvo que su propia ficha declare una
licencia compatible (Public Domain, CC0, CC BY, CC BY-SA — nunca CC
BY-NC, CC BY-ND, ni nada sin información clara de derechos), siguiendo
la matriz de "Estudio de fuentes visuales de dominio público" (informe
verificado del 22/07/2026).

Fuentes implementadas:
- Wikimedia Commons (API pública, sin clave, con metadatos de licencia
  estructurados y fiables — la fuente que el informe de fuentes de la
  Guerra Civil marca como más operativa). Otras fuentes de ese informe
  (Europeana, Library of Congress, BNE, PARES) no están aquí: Europeana
  necesita una clave de API que no tenemos configurada, y LOC/BNE/PARES
  no tienen metadatos de derechos lo bastante fiables para filtrar
  automáticamente sin revisión humana — quedan fuera a propósito.
- NASA Image and Video Library (images-api.nasa.gov, sin clave). Casi
  todo el contenido de la NASA es dominio público por ser obra del
  gobierno de EE. UU., SALVO excepciones puntuales que la propia API
  marca con un campo "copyright" — cualquier resultado con ese campo
  presente se descarta automáticamente, igual de estricto que con
  Wikimedia Commons. Solo imágenes por ahora (el vídeo de la NASA
  requiere una segunda petición por elemento para sacar el archivo real
  y no se ha implementado todavía).

Cada descarga se registra en un log de auditoría (JSON) con la ficha de
control completa (autor, licencia, URL permanente, fecha) — sin este
registro no hay forma de demostrar después que el uso era legítimo.
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "TelvornAutomation/1.0 (music video production tool)"


def _api_get(params: dict) -> dict:
    params = {**params, "format": "json"}
    resp = requests.get(COMMONS_API, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _license_verdict(license_tag: str, license_short_name: str = ""):
    """
    Clasifica una licencia según la matriz del informe. Devuelve una
    etiqueta corta ("Public Domain"/"CC0"/"CC BY"/"CC BY-SA") si es
    apta para uso comercial y edición, o None si hay que descartarla
    (CC BY-NC, CC BY-ND, protegida, o sin información suficiente).
    """
    tag = (license_tag or license_short_name or "").lower().strip()
    if not tag:
        return None
    parts = set(re.split(r"[\s\-,/]+", tag))

    if parts & {"nc", "noncommercial", "non-commercial"}:
        return None
    if parts & {"nd", "noderivatives", "noderivs", "no-derivatives"}:
        return None
    if "cc0" in parts or tag == "cc0":
        return "CC0"
    if {"public", "domain"} <= parts or "pd" in parts:
        return "Public Domain"
    if "sa" in parts and "by" in parts:
        return "CC BY-SA"
    if "by" in parts and ("cc" in parts or "creative" in parts):
        return "CC BY"
    return None


def search_wikimedia_commons(
    query: str,
    limit: int = 20,
    min_short_side: int = 720,
    exclude_urls: set = None,
):
    """
    Busca `query` en Wikimedia Commons (namespace de archivos) y
    devuelve solo los resultados con licencia compatible y resolución
    mínima, cada uno como un dict con la ficha de control completa:
    id, title, author, date, institution, source_url, license,
    license_url, commercial_ok, derivatives_ok, download_url, width,
    height. `exclude_urls`: URLs de descarga ya usadas antes (para no
    repetir la misma imagen en el mismo LP o entre temas).
    """
    exclude_urls = exclude_urls or set()
    search_data = _api_get({
        "action": "query", "list": "search", "srsearch": query,
        "srnamespace": 6, "srlimit": min(limit * 2, 50),
    })
    titles = [r["title"] for r in search_data.get("query", {}).get("search", [])]
    if not titles:
        return []

    results = []
    # la API acepta hasta 50 títulos por llamada (titles= separados por "|")
    for i in range(0, len(titles), 50):
        batch = titles[i:i + 50]
        info_data = _api_get({
            "action": "query", "titles": "|".join(batch),
            "prop": "imageinfo", "iiprop": "url|extmetadata|size",
        })
        pages = info_data.get("query", {}).get("pages", {})
        for page in pages.values():
            imageinfo = page.get("imageinfo")
            if not imageinfo:
                continue
            info = imageinfo[0]
            em = info.get("extmetadata", {})

            download_url = info.get("url")
            if not download_url or download_url in exclude_urls:
                continue

            width, height = info.get("width", 0), info.get("height", 0)
            if min(width, height) < min_short_side:
                continue

            license_tag = em.get("License", {}).get("value", "")
            license_short = em.get("LicenseShortName", {}).get("value", "")
            verdict = _license_verdict(license_tag, license_short)
            if not verdict:
                continue

            results.append({
                "id": f"WC_{page.get('pageid')}",
                "title": _strip_html(em.get("ObjectName", {}).get("value") or page.get("title", "")),
                "author": _strip_html(em.get("Artist", {}).get("value", "")) or "Desconocido/anónimo",
                "date": _strip_html(em.get("DateTimeOriginal", {}).get("value", "")) or _strip_html(em.get("DateTime", {}).get("value", "")),
                "institution": "Wikimedia Commons" + (f" — {_strip_html(em.get('Credit', {}).get('value', ''))}" if em.get("Credit") else ""),
                "source_url": info.get("descriptionurl", ""),
                "license": verdict,
                "license_raw": license_short or license_tag,
                "license_url": em.get("LicenseUrl", {}).get("value", ""),
                "commercial_ok": True,
                "derivatives_ok": True,
                "download_url": download_url,
                "width": width,
                "height": height,
            })
            if len(results) >= limit:
                return results
    return results


NASA_API = "https://images-api.nasa.gov/search"


def generate_nasa_query(track_title: str, context: str) -> str:
    """
    Convierte el título/contexto de un tema (en español, pensado para
    humanos) en un término de búsqueda en inglés efectivo contra la
    biblioteca de la NASA — la búsqueda de la NASA funciona mucho mejor
    con términos concretos en inglés (ej. "Saturn rings Cassini") que
    con frases largas o en español.
    """
    from src.anthropic_utils import call_claude_json

    system = (
        "Eres un asistente que convierte la descripción de un tema musical "
        "en un término de búsqueda corto y efectivo en INGLÉS para la "
        "biblioteca de imágenes/vídeo de la NASA (images.nasa.gov). "
        "El término debe ser concreto (objeto astronómico + característica "
        "visual, ej. 'Saturn rings Cassini', 'Andromeda galaxy Hubble', "
        "'Jupiter Great Red Spot'), de 2 a 5 palabras, sin explicaciones. "
        "Responde ÚNICAMENTE con JSON: {\"query\": \"...\"}"
    )
    user = f"Título del tema: {track_title}\nContexto: {context}"
    result = call_claude_json(system, user, max_tokens=200, model="claude-sonnet-5")
    return result.get("query", track_title)


def search_nasa_images(
    query: str,
    limit: int = 20,
    min_short_side: int = 720,
    exclude_urls: set = None,
):
    """
    Busca `query` en la biblioteca de imágenes de la NASA. Descarta
    cualquier resultado cuya ficha traiga un campo "copyright" (las
    contadas excepciones no gubernamentales que la propia NASA marca) y
    cualquiera por debajo de `min_short_side`. Devuelve la misma forma de
    ficha que search_wikimedia_commons, compatible con download_candidate.
    """
    exclude_urls = exclude_urls or set()
    resp = requests.get(
        NASA_API, params={"q": query, "media_type": "image"},
        headers={"User-Agent": USER_AGENT}, timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("collection", {}).get("items", [])

    results = []
    for item in items:
        if not item.get("data"):
            continue
        data = item["data"][0]
        if data.get("copyright"):
            continue

        # el enlace "canonical" (~orig) es la máxima calidad disponible;
        # si no viene marcado así, se coge el de mayor resolución.
        image_links = [
            l for l in item.get("links", [])
            if l.get("render") == "image" and l.get("href")
        ]
        if not image_links:
            continue
        best = next((l for l in image_links if l.get("rel") == "canonical"), None)
        if not best:
            best = max(image_links, key=lambda l: l.get("width", 0) or 0)

        download_url = best["href"]
        if download_url in exclude_urls:
            continue
        width, height = best.get("width", 0), best.get("height", 0)
        if min(width, height) < min_short_side:
            continue

        results.append({
            "id": f"NASA_{data.get('nasa_id')}",
            "title": data.get("title", ""),
            "author": data.get("secondary_creator") or f"NASA/{data.get('center', '')}".rstrip("/"),
            "date": data.get("date_created", ""),
            "institution": f"NASA{(' — ' + data['center']) if data.get('center') else ''}",
            "source_url": f"https://images.nasa.gov/details/{data.get('nasa_id')}",
            "license": "Public Domain (NASA)",
            "license_raw": "U.S. Government Work — no copyright field present",
            "license_url": "https://www.nasa.gov/nasa-brand-center/images-and-media/",
            "commercial_ok": True,
            "derivatives_ok": True,
            "download_url": download_url,
            "width": width,
            "height": height,
        })
        if len(results) >= limit:
            break
    return results


# orden de preferencia de calidad para vídeo: "medium" es de sobra para
# un fondo de vídeo musical (se reescala igualmente en ffmpeg) y pesa
# mucho menos que "large"/"orig" -- de hasta 15x menos en pruebas reales.
_VIDEO_QUALITY_PREFERENCE = ("medium", "small", "orig", "large", "mobile", "preview")


def search_nasa_videos(
    query: str,
    limit: int = 10,
    exclude_urls: set = None,
):
    """
    Busca vídeo real (no imágenes) en la biblioteca de la NASA. Cada
    resultado de la búsqueda solo trae miniaturas, así que hay que pedir
    el manifiesto de archivos (`item["href"]`) de cada candidato para
    sacar el .mp4 real -- por eso es más lento que la búsqueda de
    imágenes y se limita a los primeros candidatos sin copyright. Misma
    ficha de control que search_nasa_images/search_wikimedia_commons.
    """
    exclude_urls = exclude_urls or set()
    resp = requests.get(
        NASA_API, params={"q": query, "media_type": "video"},
        headers={"User-Agent": USER_AGENT}, timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("collection", {}).get("items", [])

    results = []
    for item in items:
        if len(results) >= limit:
            break
        if not item.get("data") or not item.get("href"):
            continue
        data = item["data"][0]
        if data.get("copyright"):
            continue

        try:
            manifest_resp = requests.get(item["href"], headers={"User-Agent": USER_AGENT}, timeout=30)
            manifest_resp.raise_for_status()
            file_urls = manifest_resp.json()
        except (requests.exceptions.RequestException, ValueError):
            continue

        mp4_urls = [u for u in file_urls if u.lower().endswith(".mp4")]
        download_url = None
        for tier in _VIDEO_QUALITY_PREFERENCE:
            match = next((u for u in mp4_urls if u.lower().endswith(f"~{tier}.mp4")), None)
            if match:
                download_url = match.replace("http://", "https://", 1)
                break
        if not download_url or download_url in exclude_urls:
            continue

        results.append({
            "id": f"NASA_{data.get('nasa_id')}",
            "title": data.get("title", ""),
            "author": data.get("secondary_creator") or f"NASA/{data.get('center', '')}".rstrip("/"),
            "date": data.get("date_created", ""),
            "institution": f"NASA{(' — ' + data['center']) if data.get('center') else ''}",
            "source_url": f"https://images.nasa.gov/details/{data.get('nasa_id')}",
            "license": "Public Domain (NASA)",
            "license_raw": "U.S. Government Work — no copyright field present",
            "license_url": "https://www.nasa.gov/nasa-brand-center/images-and-media/",
            "commercial_ok": True,
            "derivatives_ok": True,
            "download_url": download_url,
            "width": None,
            "height": None,
        })
    return results


def gather_nasa_assets(
    query: str, out_dir: str, log_path: str = None,
    n_images: int = 3, n_videos: int = 2, exclude_urls: set = None,
):
    """
    Busca y descarga una mezcla de imágenes y vídeo real de la NASA para
    `query` -- pensado para alimentar directamente una portada de vídeo
    con varias imágenes/clips (cada uno con su propio movimiento de
    cámara o reproducción real), como ya soporta generate_main_video.
    Devuelve la lista de rutas locales descargadas, en el mismo orden en
    que deberían reproducirse (imágenes primero, luego vídeo). Actualiza
    `exclude_urls` in-place con lo ya usado, para no repetir entre temas.
    """
    exclude_urls = exclude_urls if exclude_urls is not None else set()
    downloaded = []

    for candidate in search_nasa_images(query, limit=n_images, exclude_urls=exclude_urls):
        downloaded.append(download_candidate(candidate, out_dir, log_path))
        exclude_urls.add(candidate["download_url"])

    for candidate in search_nasa_videos(query, limit=n_videos, exclude_urls=exclude_urls):
        downloaded.append(download_candidate(candidate, out_dir, log_path))
        exclude_urls.add(candidate["download_url"])

    return downloaded


def download_candidate(candidate: dict, out_dir: str, log_path: str = None) -> str:
    """
    Descarga `candidate["download_url"]` a `out_dir` y, si se pasa
    `log_path`, añade su ficha de control completa a ese archivo JSON
    (creándolo si no existe) — registro de auditoría de qué se usó, con
    qué licencia y de dónde, para poder demostrarlo después ante
    YouTube, una distribuidora o un reclamante.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(candidate["download_url"]).suffix or ".jpg"
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", candidate["id"])
    out_path = out_dir / f"{safe_id}{ext}"

    # el CDN de Wikimedia a veces devuelve 429 (límite de peticiones)
    # ante ráfagas de descargas — normal al bajar varias imágenes
    # seguidas, se reintenta con espera creciente en vez de fallar.
    last_exc = None
    for attempt, wait in enumerate((0, 3, 8)):
        if wait:
            time.sleep(wait)
        try:
            resp = requests.get(candidate["download_url"], headers={"User-Agent": USER_AGENT}, timeout=60)
            resp.raise_for_status()
            last_exc = None
            break
        except requests.exceptions.HTTPError as e:
            last_exc = e
            if e.response is not None and e.response.status_code == 429:
                continue
            raise
    if last_exc:
        raise last_exc
    out_path.write_bytes(resp.content)

    if log_path:
        log_path = Path(log_path)
        entries = []
        if log_path.exists():
            entries = json.loads(log_path.read_text(encoding="utf-8"))
        entries.append({
            **candidate,
            "downloaded_to": str(out_path),
            "downloaded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    return str(out_path)
