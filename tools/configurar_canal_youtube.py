"""
configurar_canal_youtube.py — asistente para ajustar la marca del canal
(palabras clave + descripción del "Acerca de"), una sola vez (o cada vez
que quieras cambiarlas).

Requiere haber configurado antes la subida a YouTube (ver README.md).

Uso:
    python tools/configurar_canal_youtube.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    secciones_raw = input(
        "\n¿Organizar también la página de inicio del canal en secciones "
        "(\"Últimos vídeos\", \"Más populares\"...; \"Álbumes\" se crea sola "
        "la primera vez que subas un LP)? [s/N]: "
    ).strip().lower()
    quiere_secciones = secciones_raw.startswith("s")

    if not keywords and not description and not quiere_secciones:
        print("No has indicado nada que cambiar.")
        return

    youtube = get_authenticated_service()

    if keywords or description:
        update_channel_branding(youtube, keywords=keywords, description=description)
        print("Ajustes de marca del canal actualizados.")

    if quiere_secciones:
        from src.youtube_sections import ensure_builtin_section
        ensure_builtin_section(youtube, "recentUploads", position=0)
        ensure_builtin_section(youtube, "popularUploads", position=1)
        print(
            'Secciones "Últimos vídeos" y "Más populares" creadas (si no '
            'existían ya). La sección "Álbumes" se crea sola, con la lista '
            "de cada LP, la primera vez que subas uno con procesar_lp.py."
        )

    print("\nListo.")


if __name__ == "__main__":
    main()
