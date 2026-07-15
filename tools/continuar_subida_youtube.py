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

    upload_lp_schedule(
        schedule, schedule_path, thumbnails=thumbnails, playlist_id=playlist_id,
        youtube=youtube, link_block=config.get("link_block", ""),
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
