"""
tiktok_auth.py
Gestión del token de TikTok (OAuth2): la autorización inicial (ver
tools/autorizar_tiktok.py) guarda el primer access_token/refresh_token en
config/tiktok_token.json (gitignored, nunca se sube al repositorio); a
partir de ahí, get_access_token() lo renueva solo cuando ya ha caducado,
sin que haga falta volver a autorizar nada a mano.
"""

import json
import time
from pathlib import Path

from src.tiktok_uploader import refresh_access_token

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = REPO_ROOT / "config" / "tiktok_token.json"

# margen antes de la caducidad real para renovar con tiempo de sobra
_REFRESH_MARGIN_SECONDS = 60


def save_token(data: dict):
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = dict(data)
    data["obtained_at"] = time.time()
    TOKEN_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_access_token(client_key: str, client_secret: str) -> str:
    """
    Devuelve un access_token válido, renovándolo solo si el guardado ya
    ha caducado (o está a punto). Lanza un error claro si todavía no se
    ha hecho la autorización inicial.
    """
    if not TOKEN_PATH.exists():
        raise RuntimeError(
            "No hay ningún token de TikTok guardado todavía -- ejecuta primero "
            "'python tools/autorizar_tiktok.py' para la autorización inicial (una sola vez)."
        )
    data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    expires_at = data["obtained_at"] + data["expires_in"]
    if time.time() < expires_at - _REFRESH_MARGIN_SECONDS:
        return data["access_token"]

    refreshed = refresh_access_token(client_key, client_secret, data["refresh_token"])
    save_token(refreshed)
    return refreshed["access_token"]
