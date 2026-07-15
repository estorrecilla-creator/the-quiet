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

    others = sorted(
        ((pid, e) for pid, e in data.items() if pid != playlist_id),
        key=lambda pair: pair[1]["lp_title"],
    )
    if others:
        links = "\n".join(f"- {e['lp_title']}: {playlist_url(pid)}" for pid, e in others)
        parts.append(f"🎵 Más álbumes de {artist}:\n{links}")

    return "\n\n".join(parts)


def register_and_link_lp_playlist(
    youtube, group_dir, artist: str, lp_title: str, playlist_id: str,
    base_description: str, hashtags: list,
):
    """
    Registra la lista de reproducción de este LP entre las del mismo
    grupo y reconstruye la descripción de ESTA lista Y de todas las
    demás del grupo, para que se enlacen entre sí — así, según se van
    subiendo LPs nuevos, los antiguos también se actualizan solos para
    apuntar al más reciente, sin tener que tocarlos a mano.
    """
    data = _load(group_dir)
    data[playlist_id] = {
        "lp_title": lp_title,
        "base_description": base_description,
        "hashtags": hashtags or [],
    }
    for pid in data:
        full_description = _build_full_description(pid, data, artist)
        update_playlist_description(youtube, pid, full_description)
    _save(group_dir, data)
