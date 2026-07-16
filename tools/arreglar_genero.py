"""
arreglar_genero.py
Corrige el campo de género ya escrito en los audios finales de una
carpeta (AUDIO_FINAL), sin tocar el audio ni ningún otro metadato: lee lo
que ya hay en cada archivo (título, artista, álbum, año, pista...) y lo
vuelve a escribir tal cual, cambiando únicamente el género. Pensado para
cuando el género se generó mal (frases descriptivas, nombres de otros
artistas...) y hay que corregirlo en archivos que ya se generaron antes
del arreglo, sin tener que rehacer la masterización.

Uso:
    python tools/arreglar_genero.py "C:\\ruta\\a\\AUDIO_FINAL" "Progressive Rock"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mutagen.mp3 import MP3
from mutagen.wave import WAVE

from src.metadata_cleaner import clean_audio_metadata

_AUDIO_EXTENSIONS = (".wav", ".mp3")


def _text(tags, frame_id):
    frame = tags.get(frame_id)
    if not frame or not frame.text:
        return None
    return str(frame.text[0])


def _read_existing_metadata(path):
    suffix = Path(path).suffix.lower()
    audio = MP3(path) if suffix == ".mp3" else WAVE(path)
    tags = audio.tags
    if tags is None:
        raise ValueError(f"{path} no tiene metadatos que leer.")

    track_text = _text(tags, "TRCK")
    track_number, total_tracks = (None, None)
    if track_text:
        parts = track_text.split("/")
        track_number = int(parts[0]) if parts[0].isdigit() else None
        total_tracks = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None

    disc_text = _text(tags, "TPOS")
    disc_number, total_discs = (1, 1)
    if disc_text:
        parts = disc_text.split("/")
        disc_number = int(parts[0]) if parts[0].isdigit() else 1
        total_discs = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1

    year_text = _text(tags, "TDRC")
    year = int(str(year_text)[:4]) if year_text and str(year_text)[:4].isdigit() else None

    return {
        "title": _text(tags, "TIT2"),
        "artist": _text(tags, "TPE1"),
        "album": _text(tags, "TALB"),
        "album_artist": _text(tags, "TPE2"),
        "year": year,
        "track_number": track_number,
        "total_tracks": total_tracks,
        "disc_number": disc_number,
        "total_discs": total_discs,
        "composer": _text(tags, "TCOM"),
        "lyricist": _text(tags, "TEXT"),
        "publisher": _text(tags, "TPUB"),
        "copyright_text": _text(tags, "TCOP"),
        "producer": _text(tags, "TXXX:PRODUCER"),
        "phonographic_copyright": _text(tags, "TXXX:PHONOGRAPHIC_COPYRIGHT"),
    }


def fix_genre(folder, new_genre):
    folder = Path(folder)
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in _AUDIO_EXTENSIONS)
    if not files:
        print(f"No hay archivos .wav/.mp3 en {folder}")
        return

    for path in files:
        existing = _read_existing_metadata(str(path))
        if not existing["title"] or not existing["artist"]:
            print(f"  Salto {path.name}: no tiene título/artista en los metadatos, no sé qué reescribir.")
            continue
        clean_audio_metadata(str(path), genre=new_genre, **existing)
        print(f"  Género corregido en {path.name}: \"{new_genre}\"")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Uso: python tools/arreglar_genero.py "carpeta_AUDIO_FINAL" "Nuevo Genero"')
        sys.exit(1)
    fix_genre(sys.argv[1], sys.argv[2])
