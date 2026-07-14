"""
youtube_batch.py
Lógica de subida/programación a YouTube reutilizable: la usa tanto
`programar_youtube.py` (un tema suelto) como `procesar_lp.py` (toda una
tanda de temas de un LP, uno detrás de otro).
"""

import os
import subprocess
import tempfile
from pathlib import Path

from src.release_calendar import save_schedule
from src.thumbnail_template import make_track_thumbnail
from src.youtube_uploader import upload_video


def extract_thumbnail(video_path: str, t: float = 5.0):
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


def upload_schedule(
    out_dir: str,
    schedule: list,
    thumb_template: str = None,
    playlist_id: str = None,
    youtube=None,
    link_block: str = "",
    idioma: str = None,
    track_position: int = None,
):
    """
    Sube (programada) cada elemento de `schedule` (ya calculado con
    build_schedule), en orden, guardando el progreso en calendario.json
    tras cada subida — así, si el proceso se interrumpe a mitad (útil
    sobre todo subiendo un LP entero de golpe), al relanzarlo se salta lo
    que ya estaba subido en vez de duplicarlo. Devuelve el `schedule`
    actualizado con los video_id.
    """
    track_title = Path(out_dir).name.replace("_", " ")

    for item in schedule:
        if item.get("video_id"):
            print(f"-> {Path(item['video_path']).name} ya estaba subido, lo salto.")
            continue

        print(f"\n-> Subiendo {Path(item['video_path']).name} (programado para {item['publish_at_local']})...")
        thumbnail_path = None
        try:
            if thumb_template:
                thumb_out = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False).name
                thumbnail_path = make_track_thumbnail(thumb_template, track_title, thumb_out)
            elif item["kind"] == "main":
                thumbnail_path = extract_thumbnail(item["video_path"])

            video_id = upload_video(
                video_path=item["video_path"],
                title=item["title"],
                description=item["description"] + link_block,
                tags=item["tags_youtube"],
                publish_at=item["publish_at_utc"],
                thumbnail_path=thumbnail_path,
                default_language=idioma,
            )
            item["video_id"] = video_id
            save_schedule(schedule, out_dir)

            if playlist_id and item["kind"] == "main":
                from src.youtube_playlists import add_video_to_playlist
                add_video_to_playlist(youtube, playlist_id, video_id, position=track_position)
                print(f"-> Añadido a la lista de reproducción (posición {track_position}).")
        finally:
            if thumbnail_path:
                os.remove(thumbnail_path)

    return schedule
