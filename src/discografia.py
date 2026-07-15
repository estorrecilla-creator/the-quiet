"""
discografia.py
Guarda, por grupo (una carpeta MUSICA/<Grupo>/), la descripción base y
los hashtags de la lista de reproducción de cada LP ya subido, para
poder reconstruir en cualquier momento la descripción COMPLETA de todas
ellas —incluyendo enlaces cruzados a las demás listas del mismo grupo
("Más álbumes de...")— sin que ese bloque de enlaces se vaya duplicando
cada vez que se sube un LP nuevo: siempre se regenera entero a partir de
lo guardado, nunca se concatena a mano sobre lo que ya había.
"""

import json
from pathlib import Path

from src.streaming_links import build_streaming_block
from src.youtube_playlists import playlist_url, update_playlist_description

DISCOGRAFIA_FILENAME = "discografia.json"


def _discografia_path(group_dir) -> Path:
    return Path(group_dir) / DISCOGRAFIA_FILENAME


def _load(group_dir) -> dict:
    path = _discografia_path(group_dir)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save(group_dir, data: dict):
    _discografia_path(group_dir).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _build_full_description(playlist_id: str, data: dict, artist: str) -> str:
    entry = data[playlist_id]
    parts = [entry["base_description"]]
    if entry.get("hashtags"):
        parts.append(" ".join(entry["hashtags"]))

    streaming_block = build_streaming_block(entry.get("streaming_links") or {})
    if streaming_block:
        parts.append(streaming_block)

    others = sorted(
        ((pid, e) for pid, e in data.items() if pid != playlist_id),
        key=lambda pair: pair[1]["lp_title"],
    )
    if others:
        links = "\n".join(f"- {e['lp_title']}: {playlist_url(pid)}" for pid, e in others)
        parts.append(f"🎵 Más álbumes de {artist}:\n{links}")

    return "\n\n".join(parts)


def _relink_all(youtube, group_dir, data: dict, artist: str):
    for pid in data:
        full_description = _build_full_description(pid, data, artist)
        update_playlist_description(youtube, pid, full_description)
    _save(group_dir, data)


def register_and_link_lp_playlist(
    youtube, group_dir, artist: str, lp_title: str, playlist_id: str,
    base_description: str, hashtags: list, streaming_links: dict = None,
):
    """
    Registra la lista de reproducción de este LP entre las del mismo
    grupo y reconstruye la descripción de ESTA lista Y de todas las
    demás del grupo, para que se enlacen entre sí — así, según se van
    subiendo LPs nuevos, los antiguos también se actualizan solos para
    apuntar al más reciente, sin tener que tocarlos a mano. Si no se
    pasan `streaming_links` (todavía no se conocen al generar el LP, ver
    `tools/enlaces_streaming.py`), conserva los que ya hubiera guardados.
    """
    data = _load(group_dir)
    previous = data.get(playlist_id, {})
    data[playlist_id] = {
        "lp_title": lp_title,
        "base_description": base_description,
        "hashtags": hashtags or [],
        "streaming_links": streaming_links if streaming_links is not None else previous.get("streaming_links", {}),
    }
    _relink_all(youtube, group_dir, data, artist)


def update_playlist_streaming_links(youtube, group_dir, artist: str, playlist_id: str, streaming_links: dict):
    """
    Añade/actualiza los enlaces de streaming de un LP ya registrado (sin
    tocar su descripción base ni sus hashtags) y reconstruye los enlaces
    cruzados de todo el grupo. No hace nada si ese playlist todavía no
    está registrado (el LP no ha llegado a crear su lista de reproducción).
    """
    data = _load(group_dir)
    if playlist_id not in data:
        return False
    data[playlist_id]["streaming_links"] = streaming_links
    _relink_all(youtube, group_dir, data, artist)
    return True
