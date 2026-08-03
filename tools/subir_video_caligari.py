"""
subir_video_caligari.py — sube el largometraje reinterpretado de "El
gabinete del Dr. Caligari" a YouTube, con título, descripción (enlaces +
capítulos por canción) y etiquetas ya optimizados para descubrimiento.

Sube como PRIVADO por defecto (igual que el resto del pipeline) para que
lo revises tú antes de publicarlo -- cuando estés conforme, cambia la
visibilidad a "Público" desde YouTube Studio a mano, o vuelve a lanzar
este mismo script con --publish-now si quieres que lo haga directamente.

Uso:
    python tools/subir_video_caligari.py "ruta\\caligari_the_hollow_hour_en.mp4"
    python tools/subir_video_caligari.py "ruta\\caligari_the_hollow_hour_en.mp4" --publish-now
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from src.youtube_uploader import upload_video

TITLE = "The Cabinet of Dr. Caligari (1920) — Reimagined with a Full Progressive Rock Score | It Was Time"

# Capítulos por canción -- el primero DEBE ser 0:00 para que YouTube los
# reconozca como capítulos navegables. Calculados a partir de la duración
# real de cada tema del álbum, en el orden en que suenan en el vídeo
# (Tema 1 movido al final).
CHAPTERS = """0:00 The Ledger
4:17 Static Between Hands
9:05 Furnished Absence
13:43 The Man Who Owned the Weather
17:19 Verdict, Unread
21:58 The Light I Left On
25:34 Tape Loop for a Tired Name
29:42 Fragments Kept Under the Tongue
33:35 Static Between Hands (Reprise)
37:25 The Room Forgets Its Shape
41:01 Room Before the Word (Return)
43:49 Room Before the Word"""

LINKS = """▶ Listen to "The Hollow Hour" (the full album used as the score): https://www.youtube.com/playlist?list=PLEXqIAXOh13k
🎧 Stream it on Spotify / Apple Music / everywhere: https://distrokid.com/hyperfollow/itwastime/the-hollow-hour
📷 Instagram: https://www.instagram.com/iwt.official
🦋 Bluesky: https://bsky.app/profile/iwtoficial.bsky.social"""

DESCRIPTION = f""""The Cabinet of Dr. Caligari" (1920), Robert Wiene's landmark of German Expressionist horror, reimagined: the original German intertitles have been removed and replaced with new narrative captions, and the film has been rescored from beginning to end with "The Hollow Hour", the debut concept album by progressive rock band It Was Time.

No dialogue, no original score — just the film's own imagery, restructured, carrying a completely new soundtrack built for it.

{LINKS}

CHAPTERS (by song):
{CHAPTERS}

"The Cabinet of Dr. Caligari" (1920) is in the public domain. This is a non-commercial fan reinterpretation for artistic and educational purposes.

#oldschool #progressiverock #rock #terror #experimental #silentfilm #germanexpressionism #horror #artrock #conceptalbum #1920s #fullmovie #itwastime #thehollowhour #undergroundmusic"""

TAGS = [
    "the cabinet of dr caligari",
    "silent film",
    "german expressionism",
    "1920 horror movie",
    "public domain movie",
    "progressive rock",
    "concept album",
    "art rock soundtrack",
    "experimental rock",
    "old school rock",
    "horror movie soundtrack",
    "it was time band",
    "the hollow hour",
    "full movie rescore",
    "silent horror film",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video_path")
    parser.add_argument("--publish-now", action="store_true", help="Subir directamente como público, en vez de privado para revisar antes")
    parser.add_argument("--channel", default=None, help="Canal de YouTube a usar, si hace falta (ver src/youtube_uploader._token_path_for)")
    args = parser.parse_args()

    if not Path(args.video_path).exists():
        print(f"No encuentro el vídeo: {args.video_path}")
        sys.exit(1)

    privacy_status = "public" if args.publish_now else "private"
    print(f"-> Subiendo como {privacy_status}: {Path(args.video_path).name}")
    print(f"   Título: {TITLE}")

    video_id = upload_video(
        video_path=args.video_path,
        title=TITLE,
        description=DESCRIPTION,
        tags=TAGS,
        privacy_status=privacy_status,
        default_language="en",
        channel=args.channel,
    )
    print(f"\n-> Subido: https://youtube.com/watch?v={video_id}")
    if privacy_status == "private":
        print("   Está en PRIVADO -- revísalo en YouTube Studio y cámbialo a Público cuando estés conforme.")


if __name__ == "__main__":
    main()
