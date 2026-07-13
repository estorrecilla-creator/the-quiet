"""
release_calendar.py
Reparte el vídeo principal y los Shorts de un tema (ya generados en su
carpeta de output/) en un calendario de publicación: una fecha/hora para
cada uno, separadas por un número de días configurable.

Las horas se piden en hora de España (Europe/Madrid) y se convierten a UTC,
que es lo que exige la API de YouTube para `publishAt`.
"""

import json
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

MADRID_TZ = ZoneInfo("Europe/Madrid")


def find_track_outputs(out_dir):
    """
    Busca en la carpeta de salida de un tema (ej. output/Mi_Tema/) el vídeo
    principal y los Shorts, cada uno con su metadata.json. Devuelve una
    lista de dicts en el orden en que se deberían publicar (vídeo principal
    primero, luego los Shorts en orden).
    """
    out_dir = Path(out_dir)
    items = []

    main_video = out_dir / "main_video.mp4"
    main_meta = out_dir / "main_video_metadata.json"
    if main_video.exists() and main_meta.exists():
        items.append({"kind": "main", "video_path": str(main_video), "meta_path": str(main_meta)})

    shorts = sorted(
        out_dir.glob("short_*.mp4"),
        key=lambda p: int("".join(c for c in p.stem if c.isdigit()) or 0),
    )
    for short_video in shorts:
        meta_path = out_dir / f"{short_video.stem}_metadata.json"
        if meta_path.exists():
            items.append({"kind": "short", "video_path": str(short_video), "meta_path": str(meta_path)})

    if not items:
        raise ValueError(
            f"No encuentro vídeos con su metadata.json en {out_dir}. "
            "¿Es la carpeta de salida de un tema ya generado?"
        )
    return items


def build_schedule(out_dir, start_date, start_hour=18, start_minute=0, interval_days=3):
    """
    `start_date`: objeto date (o datetime) del primer envío, en hora de
    Madrid. Cada elemento posterior se publica `interval_days` días después,
    a la misma hora.
    Devuelve la lista de find_track_outputs() con dos claves añadidas:
    `publish_at_local` (hora de Madrid, legible) y `publish_at_utc`
    (RFC3339 UTC, lo que espera la API de YouTube).
    """
    items = find_track_outputs(out_dir)

    base_dt = datetime.combine(start_date, time(start_hour, start_minute), tzinfo=MADRID_TZ)

    for i, item in enumerate(items):
        local_dt = base_dt + timedelta(days=i * interval_days)

        with open(item["meta_path"], encoding="utf-8") as f:
            meta = json.load(f)

        description = meta.get("description", "")
        hashtags = meta.get("hashtags", [])
        if hashtags:
            # Los hashtags de la descripción son los que YouTube usa para
            # el descubrimiento por nicho (los 3 primeros aparecen encima
            # del título del vídeo); si no se añaden aquí, se generan pero
            # nunca llegan a subirse.
            description = description.rstrip() + "\n\n" + " ".join(hashtags)

        item["title"] = meta.get("title", "")
        item["description"] = description
        item["tags_youtube"] = meta.get("tags_youtube", [])
        item["publish_at_local"] = local_dt.strftime("%Y-%m-%d %H:%M (hora España)")
        item["publish_at_utc"] = local_dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")

    return items


def save_schedule(schedule, out_dir):
    path = Path(out_dir) / "calendario.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)
    return path


def load_schedule(out_dir):
    path = Path(out_dir) / "calendario.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)
