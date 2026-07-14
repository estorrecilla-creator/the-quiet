"""
configurar_marca_agua.py — sube el logo del canal como watermark nativo
de YouTube, una sola vez. A partir de ahí, YouTube lo pone automáticamente
en todos los vídeos largos del canal (no en los Shorts, ahí el logo va
quemado aparte, ver README).

Requiere haber configurado antes la subida a YouTube (ver README.md).

Uso:
    python configurar_marca_agua.py
"""

from pathlib import Path

from src.youtube_uploader import get_authenticated_service
from src.youtube_watermark import set_channel_watermark


def _strip_quotes(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def ask_path(prompt):
    while True:
        raw = input(f"{prompt}: ").strip()
        value = _strip_quotes(raw)
        if value and Path(value).expanduser().exists():
            return str(Path(value).expanduser())
        print(f"  No encuentro el archivo: {value}")


def main():
    print("=== Configurar marca de agua del canal (logo) ===\n")
    print(
        "Se aplicará automáticamente a todos los vídeos largos que subas a "
        "partir de ahora (no a los Shorts). Usa un PNG con fondo "
        "transparente para que quede bien integrado.\n"
    )

    logo_path = ask_path("Ruta al logo (PNG, idealmente con fondo transparente)")

    youtube = get_authenticated_service()
    set_channel_watermark(youtube, logo_path)
    print("\nListo. El logo ya está configurado como marca de agua del canal.")


if __name__ == "__main__":
    main()
