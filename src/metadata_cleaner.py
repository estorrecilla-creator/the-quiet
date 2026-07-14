"""
metadata_cleaner.py
Limpia por completo los metadatos del archivo de audio final: borra TODO
lo que traiga (título/artista/comentarios/IDs de generación/nombre de la
herramienta usada para componerlo — Suno o cualquier otra) y escribe en
su lugar solo los metadatos correctos y limpios del tema.

Un .wav puede llevar metadatos de dos formas distintas, y ninguna
herramienta las lee todas:
  - El chunk RIFF "LIST INFO" clásico — el que entienden el Explorador de
    Windows y la mayoría de comprobadores sencillos, pero con un juego de
    campos limitado (sin hueco para "productor" o "copyright fonográfico").
  - Un chunk ID3v2 embebido — el que entienden ffprobe, muchos DAW y
    algunos distribuidores, con más campos disponibles.
Se escriben las dos para máxima compatibilidad. Ambas se borran primero
por completo (incluida cualquiera que ya trajera el archivo) antes de
escribir las nuevas: si no se borra explícitamente el chunk RIFF INFO,
ffmpeg lo conserva tal cual al reetiquetar, dejando pasar cualquier
rastro que ya tuviera.

Los .mp3 solo usan ID3v2 (no tienen esta dualidad), vía mutagen.
"""

import subprocess
from pathlib import Path

from mutagen.id3 import (
    ID3,
    ID3NoHeaderError,
    TALB,
    TCOM,
    TCON,
    TCOP,
    TDRC,
    TEXT,
    TIT2,
    TPE1,
    TPUB,
    TRCK,
    TXXX,
)
from mutagen.mp3 import MP3
from mutagen.wave import WAVE


def _id3_frames(
    title, artist, album, genre, year, track_number, composer,
    lyricist, producer, publisher, copyright_text, phonographic_copyright,
):
    frames = [TIT2(encoding=3, text=title), TPE1(encoding=3, text=artist)]
    if album:
        frames.append(TALB(encoding=3, text=album))
    if genre:
        frames.append(TCON(encoding=3, text=genre))
    if year:
        frames.append(TDRC(encoding=3, text=str(year)))
    if track_number:
        frames.append(TRCK(encoding=3, text=str(track_number)))
    if composer:
        frames.append(TCOM(encoding=3, text=composer))
    if lyricist:
        frames.append(TEXT(encoding=3, text=lyricist))
    if publisher:
        frames.append(TPUB(encoding=3, text=publisher))
    if copyright_text:
        frames.append(TCOP(encoding=3, text=copyright_text))
    if producer:
        frames.append(TXXX(encoding=3, desc="PRODUCER", text=producer))
    if phonographic_copyright:
        frames.append(TXXX(encoding=3, desc="PHONOGRAPHIC_COPYRIGHT", text=phonographic_copyright))
    return frames


def clean_audio_metadata(
    audio_path: str,
    title: str,
    artist: str,
    album: str = None,
    genre: str = None,
    year: int = None,
    track_number: int = None,
    composer: str = None,
    lyricist: str = None,
    producer: str = None,
    publisher: str = None,
    copyright_text: str = None,
    phonographic_copyright: str = None,
) -> str:
    """
    Borra todos los metadatos existentes del archivo y escribe unos
    limpios con los datos que se pasen (los campos opcionales que no se
    den, simplemente no se escriben). Modifica el archivo in-place y
    devuelve la misma ruta. Funciona con .mp3 y .wav.
    """
    suffix = Path(audio_path).suffix.lower()
    frames = _id3_frames(
        title, artist, album, genre, year, track_number, composer, lyricist,
        producer, publisher, copyright_text, phonographic_copyright,
    )

    if suffix == ".mp3":
        try:
            ID3(audio_path).delete(audio_path)  # borra ID3v2 Y v1 si los hay
        except ID3NoHeaderError:
            pass
        audio = MP3(audio_path)
        audio.add_tags()
        for frame in frames:
            audio.tags.add(frame)
        audio.save()
        return audio_path

    if suffix == ".wav":
        riff_tags = {"title": title, "artist": artist}
        if album:
            riff_tags["album"] = album
        if genre:
            riff_tags["genre"] = genre
        if year:
            riff_tags["date"] = str(year)
        if track_number:
            riff_tags["track"] = str(track_number)
        if copyright_text:
            riff_tags["copyright"] = copyright_text

        tmp_out = audio_path + ".tmp.wav"
        cmd = ["ffmpeg", "-y", "-i", audio_path, "-map_metadata", "-1"]
        for key, value in riff_tags.items():
            cmd += ["-metadata", f"{key}={value}"]
        cmd += ["-c", "copy", tmp_out]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg no pudo escribir los metadatos:\n{result.stderr[-2000:]}")
        Path(tmp_out).replace(audio_path)

        audio = WAVE(audio_path)
        if audio.tags is not None:
            audio.tags.clear()
        else:
            audio.add_tags()
        for frame in frames:
            audio.tags.add(frame)
        audio.save()
        return audio_path

    raise ValueError(f"Formato no soportado para limpiar metadatos: {suffix}")


if __name__ == "__main__":
    import sys

    path, title, artist = sys.argv[1], sys.argv[2], sys.argv[3]
    clean_audio_metadata(path, title, artist)
    print(f"Metadatos limpiados: {path}")
