"""
autorizar_tiktok.py — autorización inicial de TikTok (solo hace falta
ejecutarlo UNA VEZ). Abre el navegador para iniciar sesión y autorizar la
app, recoge el código de la URL de vuelta con un pequeño servidor local,
y lo cambia por el primer access_token/refresh_token, guardándolo en
config/tiktok_token.json. A partir de ahí, todo lo demás renueva el
token solo (ver src/tiktok_auth.py).

Requiere en el .env:
    TIKTOK_CLIENT_KEY=...
    TIKTOK_CLIENT_SECRET=...
    TIKTOK_REDIRECT_URI=...   (debe coincidir EXACTAMENTE, carácter a
        carácter, con el que registraste para esta app en
        developers.tiktok.com -- si no coincide, TikTok rechaza la
        autorización)

Uso:
    python tools/autorizar_tiktok.py
"""

import http.server
import os
import sys
import urllib.parse
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from src.tiktok_auth import save_token
from src.tiktok_uploader import exchange_code_for_token

SCOPE = "video.publish"

_captured = {}


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        _captured["code"] = params.get("code", [None])[0]
        _captured["error"] = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        message = (
            "Autorización completada, ya puedes cerrar esta pestaña."
            if _captured.get("code")
            else "Autorización fallida -- vuelve a la terminal para ver el detalle."
        )
        self.wfile.write(message.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # sin ruido de peticiones HTTP en la consola


def main():
    client_key = os.environ["TIKTOK_CLIENT_KEY"]
    client_secret = os.environ["TIKTOK_CLIENT_SECRET"]
    redirect_uri = os.environ["TIKTOK_REDIRECT_URI"]

    parsed = urllib.parse.urlparse(redirect_uri)
    port = parsed.port or 80

    auth_url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": client_key,
        "scope": SCOPE,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": "the-quiet-auth",
    })
    print(f"Abriendo el navegador para autorizar la app...\nSi no se abre solo, entra en:\n{auth_url}\n")
    webbrowser.open(auth_url)

    server = http.server.HTTPServer((parsed.hostname, port), _CallbackHandler)
    print(f"Esperando la autorización en {redirect_uri} ...")
    server.handle_request()  # atiende una sola petición (la vuelta de TikTok) y sigue

    if _captured.get("error"):
        print(f"TikTok rechazó la autorización: {_captured['error']}")
        sys.exit(1)
    code = _captured.get("code")
    if not code:
        print("No se recibió ningún código de autorización -- revisa que TIKTOK_REDIRECT_URI "
              "coincide exactamente con el registrado en developers.tiktok.com.")
        sys.exit(1)

    token_data = exchange_code_for_token(client_key, client_secret, code, redirect_uri)
    save_token(token_data)
    print("Autorización completada y guardada en config/tiktok_token.json.")


if __name__ == "__main__":
    main()
