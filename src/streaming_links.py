"""
streaming_links.py
Guarda y da formato a los enlaces de streaming (Spotify, Apple Music...)
de un LP, para poder enlazarlos en YouTube en cuanto DistroKid los tenga
listos — normalmente días/semanas después de haber generado y empezado a
subir el contenido, así que se guardan y aplican aparte, no en el mismo
momento que el resto del LP.
"""

import json
from pathlib import Path

PLATFORMS = [
    ("spotify", "Spotify"),
    ("apple_music", "Apple Music"),
    ("youtube_music", "YouTube Music"),
    ("amazon_music", "Amazon Music"),
    ("deezer", "Deezer"),
    ("tidal", "Tidal"),
    ("smart_link", "Enlace agregador (DistroKid HyperFollow, feature.fm...)"),
]

LINKS_FILENAME = "enlaces_streaming.json"
BLOCK_MARKER = "🎧 Escúchalo en streaming"


def links_path(lp_dir) -> Path:
    return Path(lp_dir) / LINKS_FILENAME


def load_streaming_links(lp_dir) -> dict:
    path = links_path(lp_dir)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_streaming_links(lp_dir, links: dict):
    links_path(lp_dir).write_text(
        json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_streaming_block(links: dict) -> str:
    """
    Bloque de texto listo para pegar en una descripción (vídeo, Short o
    lista de reproducción), con un enlace por plataforma dada. Devuelve
    cadena vacía si `links` está vacío, para poder concatenarlo siempre
    sin comprobar antes.
    """
    if not links:
        return ""
    labels = dict(PLATFORMS)
    lines = [f"{labels.get(key, key)}: {url}" for key, url in links.items() if url]
    if not lines:
        return ""
    return f"{BLOCK_MARKER}:\n" + "\n".join(lines)
