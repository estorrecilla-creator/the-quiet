"""
continuar_subida_youtube.py — sube el siguiente lote de vídeos a YouTube
(el que quepa en la cuota diaria de la API), para todos los LPs de
MUSICA/ que tengan una subida confirmada y todavía pendiente.

No pregunta nada — está pensado para ejecutarse solo, una vez al día, con
la Tarea Programada de Windows (ver README, o el aviso que imprime
`procesar_lp.py` justo después de confirmar la subida de un LP). Así el
LP se termina de subir solo, respetando la cuota diaria, sin que haga
falta relanzar nada a mano cada día.

Uso:
    python tools/continuar_subida_youtube.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from src.lp_shorts_schedule import load_lp_schedule, upload_lp_schedule

MUSICA_DIR = REPO_ROOT / "MUSICA"


def _find_pending_lps():
    """
    Un LP tiene subida pendiente si existe su config_subida_youtube.json
    (se confirmó la subida en procesar_lp.py) y su calendario_youtube.json
    todavía tiene algún vídeo sin video_id.
    """
    if not MUSICA_DIR.is_dir():
        return []
    pending = []
    for config_path in MUSICA_DIR.glob("*/*/config_subida_youtube.json"):
        lp_dir = config_path.parent
        schedule_path = lp_dir / "calendario_youtube.json"
        if not schedule_path.exists():
            continue
        schedule = load_lp_schedule(schedule_path)
        if any(not item.get("video_id") for item in schedule):
            pending.append(lp_dir)
    return pending


def _process_lp(lp_dir: Path):
    schedule_path = lp_dir / "calendario_youtube.json"
    config_path = lp_dir / "config_subida_youtube.json"
    schedule = load_lp_schedule(schedule_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    print(f"\n=== {lp_dir.relative_to(REPO_ROOT)} ===")

    playlist_id = config.get("playlist_id")
    youtube = None
    if playlist_id:
        from src.youtube_uploader import get_authenticated_service
        youtube = get_authenticated_service()

    thumbnails = {int(k): v for k, v in (config.get("thumbnails") or {}).items()}
    track_positions = {int(k): v for k, v in (config.get("track_positions") or {}).items()}

    # los enlaces de streaming (Spotify, Apple Music...) normalmente
    # llegan días/semanas después de empezar a subir el LP (los añade
    # tools/enlaces_streaming.py) — se comprueban de nuevo cada día, no
    # solo en el momento en que se confirmó la subida, para que los
    # vídeos que todavía no se hayan subido ya los lleven en cuanto
    # existan.
    from src.streaming_links import load_streaming_links, build_streaming_block
    link_block = config.get("link_block", "")
    streaming_block = build_streaming_block(load_streaming_links(lp_dir))
    if streaming_block and streaming_block not in link_block:
        link_block += f"\n\n{streaming_block}"

    # lista de reproducción de Shorts: si este LP se confirmó ANTES de que
    # existiera esta función, no tendrá una todavía -- se crea aquí, una
    # sola vez, en cuanto haya conexión a YouTube (no hace falta relanzar
    # procesar_lp.py para conseguirla).
    shorts_playlist_id = config.get("shorts_playlist_id")
    if playlist_id and not shorts_playlist_id:
        from src.youtube_playlists import create_or_get_playlist, update_playlist_description, playlist_url
        main_playlist = youtube.playlists().list(part="snippet", id=playlist_id).execute()
        items = main_playlist.get("items", [])
        main_title = items[0]["snippet"]["title"] if items else lp_dir.name
        shorts_playlist_id = create_or_get_playlist(youtube, f"{main_title} — Shorts")
        shorts_description = f'Shorts de "{lp_dir.name}".\n\n▶ Escucha el álbum completo: {playlist_url(playlist_id)}'
        if streaming_block:
            shorts_description += f"\n\n{streaming_block}"
        update_playlist_description(youtube, shorts_playlist_id, shorts_description)
        config["shorts_playlist_id"] = shorts_playlist_id
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"-> Lista de reproducción de Shorts creada: {playlist_url(shorts_playlist_id)}")

    # miniatura de las listas de reproducción: se aplica una sola vez, en
    # cuanto haya una ruta guardada en la configuración (para un LP
    # confirmado antes de que existiera esta opción, basta con añadir
    # "playlist_thumbnail_path" a mano en config_subida_youtube.json).
    thumb_path = config.get("playlist_thumbnail_path")
    if thumb_path and not config.get("playlist_thumbnail_applied") and playlist_id:
        from src.youtube_playlists import set_playlist_thumbnail
        try:
            set_playlist_thumbnail(youtube, playlist_id, thumb_path)
            if shorts_playlist_id:
                set_playlist_thumbnail(youtube, shorts_playlist_id, thumb_path)
            config["playlist_thumbnail_applied"] = True
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            print("-> Miniatura puesta en las listas de reproducción.")
        except Exception as e:
            print(f"   Aviso: no se pudo poner la miniatura de las listas ({e}).")

    upload_lp_schedule(
        schedule, schedule_path, thumbnails=thumbnails, playlist_id=playlist_id,
        shorts_playlist_id=shorts_playlist_id,
        youtube=youtube, link_block=link_block,
        idioma=config.get("idioma"), track_positions=track_positions,
    )


def main():
    print(f"=== Continuar subida a YouTube — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    pending = _find_pending_lps()
    if not pending:
        print("No hay ningún LP con subida a YouTube pendiente. Nada que hacer hoy.")
        return
    for lp_dir in pending:
        _process_lp(lp_dir)


if __name__ == "__main__":
    main()
