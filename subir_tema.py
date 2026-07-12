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


def _strip_quotes(value):
    # Al arrastrar un archivo a la terminal (sobre todo en Windows), la ruta
    # llega envuelta en comillas: "C:\ruta\archivo.mp3".
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def ask(prompt, default=None, required=True):
    suffix = f" [{default}]" if default else ""
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        value = _strip_quotes(raw) if raw else default
        if value or not required:
            return value
        print("  Este dato es obligatorio.")


def ask_path(prompt, required=True):
    while True:
        value = ask(prompt, required=required)
        if not value:
            return None
        if Path(value).expanduser().exists():
            return str(Path(value).expanduser())
        print(f"  No encuentro el archivo: {value}")


def main():
    print("=== Telvorn Automation — asistente ===\n")

    audio = ask_path("Ruta al audio (mp3/wav)")
    cover = ask_path(
        "Ruta a la portada (jpg/png), o a una carpeta con varias imágenes "
        "(cada una tendrá su propio movimiento de cámara)"
    )
    artist = ask("Artista")
    title = ask("Título del tema")
    genre = ask("Género/estilo")
    context = ask("Contexto/concepto del tema")
    shorts = int(ask("Número de Shorts a generar", "3"))
    lyrics = ask_path(
        "Ruta a la letra (.srt ya sincronizado, o .txt en texto plano para "
        "sincronizar automáticamente; opcional, Enter para omitir)",
        required=False,
    )
    lyrics_offset = 0.0
    if lyrics:
        offset_raw = ask(
            "Ajuste manual de la letra en segundos (positivo = retrasa, "
            "negativo = adelanta; Enter para no ajustar)",
            default="0",
            required=False,
        )
        try:
            lyrics_offset = float(offset_raw) if offset_raw else 0.0
        except ValueError:
            print("  Valor no válido, no se aplicará ajuste.")
            lyrics_offset = 0.0

    out_dir = process_track(
        audio, cover, artist, title, genre, context, shorts, "output",
        lyrics_path=lyrics, lyrics_offset=lyrics_offset,
    )
    print(f"\nListo. Revisa la carpeta: {out_dir}")


if __name__ == "__main__":
    main()
