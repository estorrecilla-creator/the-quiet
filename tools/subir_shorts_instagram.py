"""
subir_shorts_instagram.py — publica en Instagram (como Reels) los Shorts
de cada LP de MUSICA/ que tenga la subida a YouTube confirmada Y el uso
de Instagram activado ("instagram_enabled": true en su
config_subida_youtube.json).

Como continuar_subida_youtube.py, no pregunta nada -- pensado para
ejecutarse solo, una vez al día (por ejemplo justo después de ese mismo
script, con la misma Tarea Programada de Windows), para ir publicando en
Instagram lo que le toque hoy según el mismo calendario que ya sigue
YouTube.

Requiere en el .env: IG_USER_ID, PAGE_ACCESS_TOKEN (ver
src/meta_uploader.py para cómo conseguirlos) y las credenciales de
Cloudflare R2 (ver src/cloud_storage.py) para alojar temporalmente cada
vídeo mientras Instagram lo descarga.

Para activarlo en un LP concreto, añade a su config_subida_youtube.json:
    "instagram_enabled": true

Uso:
    python tools/subir_shorts_instagram.py
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

from src.instagram_schedule import (
    build_instagram_schedule_from_youtube,
    load_instagram_schedule,
    publish_due_instagram_items,
    save_instagram_schedule,
)

MUSICA_DIR = REPO_ROOT / "MUSICA"


def _find_instagram_lps():
    if not MUSICA_DIR.is_dir():
        return []
    lps = []
    for config_path in MUSICA_DIR.glob("*/*/config_subida_youtube.json"):
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not config.get("instagram_enabled"):
            continue
        lp_dir = config_path.parent
        if (lp_dir / "calendario_youtube.json").exists():
            lps.append(lp_dir)
    return lps


def _process_lp(lp_dir: Path, ig_user_id: str, access_token: str):
    config_path = lp_dir / "config_subida_youtube.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    youtube_schedule_path = lp_dir / "calendario_youtube.json"
    instagram_schedule_path = lp_dir / "calendario_instagram.json"

    if instagram_schedule_path.exists():
        schedule = load_instagram_schedule(instagram_schedule_path)
    else:
        schedule = build_instagram_schedule_from_youtube(youtube_schedule_path)
        save_instagram_schedule(schedule, instagram_schedule_path)
        print(
            f"-> Calendario de Instagram creado ({len(schedule)} Shorts) en "
            f"{instagram_schedule_path.relative_to(REPO_ROOT)}"
        )

    print(f"\n=== {lp_dir.relative_to(REPO_ROOT)} (Instagram) ===")
    publish_due_instagram_items(
        schedule, instagram_schedule_path, ig_user_id, access_token,
        giveaway_text=config.get("giveaway_text", ""),
    )


def main():
    print(f"=== Subida de Shorts a Instagram — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    ig_user_id = os.environ.get("IG_USER_ID")
    access_token = os.environ.get("PAGE_ACCESS_TOKEN")
    if not ig_user_id or not access_token:
        print("Faltan IG_USER_ID / PAGE_ACCESS_TOKEN en el .env -- ver src/meta_uploader.py.")
        sys.exit(1)

    lps = _find_instagram_lps()
    if not lps:
        print('No hay ningún LP con Instagram activado ("instagram_enabled": true) pendiente.')
        return
    for lp_dir in lps:
        _process_lp(lp_dir, ig_user_id, access_token)


if __name__ == "__main__":
    main()
