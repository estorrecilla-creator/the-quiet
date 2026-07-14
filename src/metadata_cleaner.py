"""
metadata_cleaner.py
Limpia por completo los metadatos del archivo de audio final: borra TODO
lo que traiga (título/artista/comentarios/IDs de generación/nombre de la
herramienta usada para componerlo — Suno o cualquier otra) y escribe en
su lugar solo los metadatos correctos y limpios del tema: título,
artista, álbum, género, año y número de pista. Se aplica como último
paso, después de masterizar/normalizar, sobre el archivo final que se
sube a YouTube/DistroKid.

Funciona con .mp3 (ID3v2, y también borra un ID3v1 si lo hubiera) y .wav
(ID3 embebido, el mecanismo estándar que usa mutagen para WAV).
"""

from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError, TALB, TCON, TDRC, TIT2, TPE1, TRCK
from mutagen.mp3 import MP3
from mutagen.wave import WAVE


def clean_audio_metadata(
    audio_path: str,
    title: str,
    artist: str,
    album: str = None,
    genre: str = None,
    year: int = None,
    track_number: int = None,
) -> str:
    """
    Borra todos los metadatos existentes del archivo y escribe unos
    limpios con los datos que se pasen (los campos opcionales que no se
    den, simplemente no se escriben). Modifica el archivo in-place y
    devuelve la misma ruta.
    """
    suffix = Path(audio_path).suffix.lower()

    if suffix == ".mp3":
        try:
            ID3(audio_path).delete(audio_path)  # borra ID3v2 Y v1 si los hay
        except ID3NoHeaderError:
            pass
        audio = MP3(audio_path)
        audio.add_tags()
        tags = audio.tags
    elif suffix == ".wav":
        audio = WAVE(audio_path)
        if audio.tags is not None:
            audio.tags.clear()
        else:
            audio.add_tags()
        tags = audio.tags
    else:
        raise ValueError(f"Formato no soportado para limpiar metadatos: {suffix}")

    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    if album:
        tags.add(TALB(encoding=3, text=album))
    if genre:
        tags.add(TCON(encoding=3, text=genre))
    if year:
        tags.add(TDRC(encoding=3, text=str(year)))
    if track_number:
        tags.add(TRCK(encoding=3, text=str(track_number)))

    audio.save()
    return audio_path


if __name__ == "__main__":
    import sys

    path, title, artist = sys.argv[1], sys.argv[2], sys.argv[3]
    clean_audio_metadata(path, title, artist)
    print(f"Metadatos limpiados: {path}")
