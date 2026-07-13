"""
configurar_canal_youtube.py — asistente para ajustar la marca del canal
(palabras clave + descripción del "Acerca de"), una sola vez (o cada vez
que quieras cambiarlas).

Requiere haber configurado antes la subida a YouTube (ver README.md).

Uso:
    python configurar_canal_youtube.py
"""

from src.youtube_uploader import get_authenticated_service
from src.youtube_channel import update_channel_branding


def _strip_quotes(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def ask(prompt, required=True):
    while True:
        raw = input(f"{prompt}: ").strip()
        value = _strip_quotes(raw) if raw else None
        if value or not required:
            return value
        print("  Este dato es obligatorio.")


def main():
    print("=== Configurar canal de YouTube ===\n")

    keywords = ask(
        "Palabras clave del canal, separadas por espacios (usa comillas "
        "para frases: \"progressive rock\" \"atmospheric rock\" \"concept "
        "album\"...; Enter para no tocarlas)",
        required=False,
    )
    description = ask(
        "Descripción del canal (el 'Acerca de'; Enter para no tocarla)",
        required=False,
    )

    if not keywords and not description:
        print("No has indicado nada que cambiar.")
        return

    youtube = get_authenticated_service()
    update_channel_branding(youtube, keywords=keywords, description=description)
    print("\nListo. Ajustes del canal actualizados.")


if __name__ == "__main__":
    main()
