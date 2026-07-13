"""
programar_youtube.py — asistente para programar la publicación en YouTube
de un tema ya generado (vídeo principal + Shorts).

No sube nada "a ciegas": primero calcula el calendario y te lo enseña, lo
guarda en la carpeta del tema (calendario.json) para que lo revises, y solo
sube/programa de verdad si confirmas.

Requiere haber configurado antes la subida a YouTube (ver README.md,
sección de configuración de config/client_secret.json).

Uso:
    python programar_youtube.py
"""

import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from src.release_calendar import build_schedule, save_schedule, load_schedule


def _extract_thumbnail(video_path, t=5.0):
    """
    Saca un fotograma del vídeo como miniatura personalizada (sin esto,
    YouTube pone una a medias del vídeo elegida al azar, peor para el
    click-through). Devuelve None si ffmpeg falla, sin bloquear la subida.
    """
    out_path = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
    result = subprocess.run(
        ["ffmpeg", "-y", "-ss", str(t), "-i", video_path, "-frames:v", "1", "-q:v", "2", out_path],
        capture_output=True,
    )
    if result.returncode != 0 or not os.path.getsize(out_path):
        return None
    return out_path


def _strip_quotes(value):
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
    print("=== Programar publicación en YouTube ===\n")

    out_dir = ask("Carpeta de salida del tema (ej. output/Mi_Tema)")
    if not Path(out_dir).is_dir():
        print(f"  No encuentro la carpeta: {out_dir}")
        sys.exit(1)

    calendario_path = Path(out_dir) / "calendario.json"
    if calendario_path.exists():
        usar = ask(
            f"Ya existe un calendario guardado en {calendario_path}. "
            "¿Reutilizarlo (r) o generar uno nuevo (n)?", "r"
        ).lower()
        if usar.startswith("r"):
            schedule = load_schedule(out_dir)
        else:
            schedule = None
    else:
        schedule = None

    if schedule is None:
        fecha_raw = ask("Fecha del primer envío (dd/mm/aaaa)")
        fecha = datetime.strptime(fecha_raw, "%d/%m/%Y").date()
        hora_raw = ask("Hora del primer envío, en hora de España (HH:MM)", "18:00")
        hh, mm = (int(x) for x in hora_raw.split(":"))
        interval = int(ask("Días entre cada publicación (vídeo principal, short 1, short 2...)", "3"))

        schedule = build_schedule(out_dir, fecha, hh, mm, interval_days=interval)
        save_schedule(schedule, out_dir)

    print("\n--- Calendario propuesto ---")
    for item in schedule:
        print(f"  [{item['kind']:5}] {item['publish_at_local']}  ->  {Path(item['video_path']).name}")
        print(f"           título: {item['title']}")
    print(f"\nGuardado en: {calendario_path}")
    print("Puedes editar ese archivo a mano (campo publish_at_utc) antes de programar.")

    confirmar = ask(
        "\n¿Subir y programar esto en YouTube ahora? (necesitas tener "
        "config/client_secret.json ya configurado) [s/N]", "n"
    ).lower()
    if not confirmar.startswith("s"):
        print("No se ha subido nada. Vuelve a ejecutar este asistente cuando quieras "
              "confirmarlo (elige 'r' para reutilizar el calendario guardado).")
        return

    idioma = ask(
        "Idioma principal del contenido (es/en...; Enter para no indicarlo)",
        required=False,
    )

    thumb_template = ask_path(
        "Ruta a una plantilla de miniatura (portada del LP con el logo; se "
        "le sustituye el texto del álbum por el título del tema; Enter para "
        "usar en su lugar un fotograma del vídeo)",
        required=False,
    )
    track_title = Path(out_dir).name.replace("_", " ")

    from src.youtube_uploader import upload_video

    schedule = load_schedule(out_dir)  # por si se editó a mano
    for item in schedule:
        print(f"\n-> Subiendo {Path(item['video_path']).name} (programado para {item['publish_at_local']})...")
        if thumb_template:
            thumb_out = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
            from src.thumbnail_template import make_track_thumbnail
            thumbnail_path = make_track_thumbnail(thumb_template, track_title, thumb_out)
        else:
            thumbnail_path = _extract_thumbnail(item["video_path"]) if item["kind"] == "main" else None
        try:
            upload_video(
                video_path=item["video_path"],
                title=item["title"],
                description=item["description"],
                tags=item["tags_youtube"],
                publish_at=item["publish_at_utc"],
                thumbnail_path=thumbnail_path,
                default_language=idioma,
            )
        finally:
            if thumbnail_path:
                os.remove(thumbnail_path)

    print("\nListo. Los vídeos están subidos (ocultos) y se publicarán solos en su fecha.")


if __name__ == "__main__":
    main()
