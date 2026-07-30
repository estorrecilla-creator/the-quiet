"""
subir_shorts_tiktok.py — publica en TikTok los Shorts de cada LP de
MUSICA/ que tenga la subida a YouTube confirmada Y el uso de TikTok
activado ("tiktok_enabled": true en su config_subida_youtube.json).

Como continuar_subida_youtube.py, no pregunta nada -- pensado para
ejecutarse solo, una vez al día (por ejemplo justo después de ese mismo
script, con la misma Tarea Programada de Windows).

AVISO IMPORTANTE: mientras la app de TikTok no haya pasado la revisión
("audit") del scope `video.publish`, todo lo publicado aquí sale
forzosamente en modo PRIVADO (solo visible para el propio dueño de la
cuenta) -- ver src/tiktok_uploader.py.

Requiere haber hecho ya la autorización inicial una vez
(python tools/autorizar_tiktok.py) y tener en el .env:
    TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET

Para activarlo en un LP concreto, añade a su config_subida_youtube.json:
    "tiktok_enabled": true

Uso:
    python tools/subir_shorts_tiktok.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from src.tiktok_auth import get_access_token
from src.tiktok_schedule import (
    build_tiktok_schedule_from_youtube,
    load_tiktok_schedule,
    publish_due_tiktok_items,
    save_tiktok_schedule,
)

MUSICA_DIR = REPO_ROOT / "MUSICA"


def _find_tiktok_lps():
    if not MUSICA_DIR.is_dir():
        return []
    lps = []
    for config_path in MUSICA_DIR.glob("*/*/config_subida_youtube.json"):
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not config.get("tiktok_enabled"):
            continue
        lp_dir = config_path.parent
        if (lp_dir / "calendario_youtube.json").exists():
            lps.append(lp_dir)
    return lps


def _process_lp(lp_dir: Path, access_token: str):
    config_path = lp_dir / "config_subida_youtube.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    youtube_schedule_path = lp_dir / "calendario_youtube.json"
    tiktok_schedule_path = lp_dir / "calendario_tiktok.json"

    existed_before = tiktok_schedule_path.exists()
    existing_schedule = load_tiktok_schedule(tiktok_schedule_path) if existed_before else None
    schedule = build_tiktok_schedule_from_youtube(youtube_schedule_path, existing_schedule=existing_schedule)
    save_tiktok_schedule(schedule, tiktok_schedule_path)
    if not existed_before:
        print(
            f"-> Calendario de TikTok creado ({len(schedule)} Shorts) en "
            f"{tiktok_schedule_path.relative_to(REPO_ROOT)}"
        )

    print(f"\n=== {lp_dir.relative_to(REPO_ROOT)} (TikTok) ===")
    publish_due_tiktok_items(
        schedule, tiktok_schedule_path, access_token,
        giveaway_text=config.get("giveaway_text", ""),
        privacy_level=config.get("tiktok_privacy_level", "SELF_ONLY"),
    )


def main():
    print(f"=== Subida de Shorts a TikTok — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")
    if not client_key or not client_secret:
        print("Faltan TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET en el .env.")
        sys.exit(1)

    try:
        access_token = get_access_token(client_key, client_secret)
    except RuntimeError as e:
        print(str(e))
        sys.exit(1)

    lps = _find_tiktok_lps()
    if not lps:
        print('No hay ningún LP con TikTok activado ("tiktok_enabled": true) pendiente.')
        return
    for lp_dir in lps:
        _process_lp(lp_dir, access_token)


if __name__ == "__main__":
    main()
