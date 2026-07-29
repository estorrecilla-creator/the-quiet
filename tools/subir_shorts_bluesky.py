"""
subir_shorts_bluesky.py — publica en Bluesky los Shorts de cada LP de
MUSICA/ que tenga la subida a YouTube confirmada Y el uso de Bluesky
activado ("bluesky_enabled": true en su config_subida_youtube.json).

Como continuar_subida_youtube.py, no pregunta nada -- pensado para
ejecutarse solo, una vez al día (por ejemplo justo después de ese mismo
script, con la misma Tarea Programada de Windows), para ir publicando en
Bluesky lo que le toque hoy según el mismo calendario que ya sigue
YouTube.

Requiere en el .env:
    BLUESKY_HANDLE=iwt.oficial.bsky.social (o tu dominio propio)
    BLUESKY_APP_PASSWORD=... (contraseña de APLICACIÓN, nunca la
        contraseña normal de la cuenta -- se genera en Bluesky desde
        Configuración -> Contraseñas de aplicaciones, sin pedir permiso
        a nadie ni esperar ninguna revisión)

Para activarlo en un LP concreto, añade a su config_subida_youtube.json:
    "bluesky_enabled": true

Uso:
    python tools/subir_shorts_bluesky.py
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

from src.bluesky_schedule import (
    build_bluesky_schedule_from_youtube,
    load_bluesky_schedule,
    publish_due_bluesky_items,
    save_bluesky_schedule,
)

MUSICA_DIR = REPO_ROOT / "MUSICA"


def _find_bluesky_lps():
    if not MUSICA_DIR.is_dir():
        return []
    lps = []
    for config_path in MUSICA_DIR.glob("*/*/config_subida_youtube.json"):
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not config.get("bluesky_enabled"):
            continue
        lp_dir = config_path.parent
        if (lp_dir / "calendario_youtube.json").exists():
            lps.append(lp_dir)
    return lps


def _process_lp(lp_dir: Path, handle: str, app_password: str):
    config_path = lp_dir / "config_subida_youtube.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    youtube_schedule_path = lp_dir / "calendario_youtube.json"
    bluesky_schedule_path = lp_dir / "calendario_bluesky.json"

    existed_before = bluesky_schedule_path.exists()
    existing_schedule = load_bluesky_schedule(bluesky_schedule_path) if existed_before else None
    # se recalcula en CADA ejecución (no solo la primera vez) para que, si
    # el LP se reprograma más adelante (tools/reprogramar_lp.py), este
    # calendario recoja las fechas nuevas de lo que aún no se ha
    # publicado -- lo ya publicado se conserva tal cual, ver el docstring
    # de build_bluesky_schedule_from_youtube.
    schedule = build_bluesky_schedule_from_youtube(youtube_schedule_path, existing_schedule=existing_schedule)
    save_bluesky_schedule(schedule, bluesky_schedule_path)
    if not existed_before:
        print(
            f"-> Calendario de Bluesky creado ({len(schedule)} Shorts) en "
            f"{bluesky_schedule_path.relative_to(REPO_ROOT)}"
        )

    print(f"\n=== {lp_dir.relative_to(REPO_ROOT)} (Bluesky) ===")
    publish_due_bluesky_items(
        schedule, bluesky_schedule_path, handle, app_password,
        giveaway_text=config.get("giveaway_text", ""),
        youtube_schedule_path=youtube_schedule_path,
    )


def main():
    print(f"=== Subida de Shorts a Bluesky — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    handle = os.environ.get("BLUESKY_HANDLE")
    app_password = os.environ.get("BLUESKY_APP_PASSWORD")
    if not handle or not app_password:
        print("Faltan BLUESKY_HANDLE / BLUESKY_APP_PASSWORD en el .env -- ver src/bluesky_uploader.py.")
        sys.exit(1)

    lps = _find_bluesky_lps()
    if not lps:
        print('No hay ningún LP con Bluesky activado ("bluesky_enabled": true) pendiente.')
        return
    for lp_dir in lps:
        _process_lp(lp_dir, handle, app_password)


if __name__ == "__main__":
    main()
