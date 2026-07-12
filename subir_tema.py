"""
subir_tema.py — asistente interactivo.

Te hace unas preguntas (audio, portada, artista, título, género, contexto) y
genera el vídeo principal, los Shorts y los metadatos, sin que tengas que
recordar los parámetros de main.py.

Uso:
    python subir_tema.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

if not os.environ.get("ANTHROPIC_API_KEY"):
    print(
        "Falta ANTHROPIC_API_KEY. Copia .env.example a .env y añade tu "
        "clave (ANTHROPIC_API_KEY=sk-ant-...) antes de continuar."
    )
    sys.exit(1)

from main import process_track


def ask(prompt, default=None, required=True):
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip() or default
        if value or not required:
            return value
        print("  Este dato es obligatorio.")


def ask_path(prompt):
    while True:
        value = ask(prompt)
        if Path(value).expanduser().exists():
            return str(Path(value).expanduser())
        print(f"  No encuentro el archivo: {value}")


def main():
    print("=== Telvorn Automation — asistente ===\n")

    audio = ask_path("Ruta al audio (mp3/wav)")
    cover = ask_path("Ruta a la portada (jpg/png)")
    artist = ask("Artista")
    title = ask("Título del tema")
    genre = ask("Género/estilo")
    context = ask("Contexto/concepto del tema")
    shorts = int(ask("Número de Shorts a generar", "3"))

    out_dir = process_track(audio, cover, artist, title, genre, context, shorts, "output")
    print(f"\nListo. Revisa la carpeta: {out_dir}")


if __name__ == "__main__":
    main()
