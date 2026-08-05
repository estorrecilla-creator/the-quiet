"""
subir_video_caligari.py — sube el largometraje reinterpretado de "El
gabinete del Dr. Caligari" a YouTube, con título, descripción (enlaces +
capítulos por canción) y etiquetas ya optimizados para descubrimiento,
en inglés o en español según el vídeo que estés subiendo (--lang).

Sube como PRIVADO por defecto (igual que el resto del pipeline) para que
lo revises tú antes de publicarlo -- cuando estés conforme, cambia la
visibilidad a "Público" desde YouTube Studio a mano, o vuelve a lanzar
este mismo script con --publish-now si quieres que lo haga directamente.

Uso:
    python tools/subir_video_caligari.py "ruta\\caligari_the_hollow_hour_en.mp4" --lang en
    python tools/subir_video_caligari.py "ruta\\caligari_the_hollow_hour_es.mp4" --lang es
    python tools/subir_video_caligari.py "ruta\\caligari_the_hollow_hour_en.mp4" --lang en --publish-now
    python tools/subir_video_caligari.py "ruta\\caligari_the_hollow_hour_es.mp4" --lang es --publish-date 2026-08-07 --publish-time 20:00
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from src.youtube_uploader import upload_video

# Capítulos por canción -- el primero DEBE ser 0:00 para que YouTube los
# reconozca como capítulos navegables. Calculados a partir de la duración
# real de cada tema del álbum, en el orden en que suenan en el vídeo
# (Tema 1 movido al final). Los nombres de los temas se dejan en inglés
# en las dos versiones -- son los títulos reales de las canciones, no se
# traducen.
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

LINKS_EN = """▶ Listen to "The Hollow Hour" (the full album used as the score): https://www.youtube.com/playlist?list=PLEXqIAXOh13k
🎧 Stream it on Spotify / Apple Music / everywhere: https://distrokid.com/hyperfollow/itwastime/the-hollow-hour
📷 Instagram: https://www.instagram.com/iwt.official
🦋 Bluesky: https://bsky.app/profile/iwtoficial.bsky.social"""

LINKS_ES = """▶ Escucha "The Hollow Hour" (el álbum completo usado como banda sonora): https://www.youtube.com/playlist?list=PLEXqIAXOh13k
🎧 Disponible en Spotify / Apple Music / y donde escuches música: https://distrokid.com/hyperfollow/itwastime/the-hollow-hour
📷 Instagram: https://www.instagram.com/iwt.official
🦋 Bluesky: https://bsky.app/profile/iwtoficial.bsky.social"""

METADATA = {
    "en": {
        "title": "The Cabinet of Dr. Caligari (1920) — Reimagined with a Full Progressive Rock Score | It Was Time",
        "description": f""""The Cabinet of Dr. Caligari" (1920), Robert Wiene's landmark of German Expressionist horror, reimagined: the original German intertitles have been removed and replaced with new narrative captions, and the film has been rescored from beginning to end with "The Hollow Hour", the debut concept album by progressive rock band It Was Time.

No dialogue, no original score — just the film's own imagery, restructured, carrying a completely new soundtrack built for it.

{LINKS_EN}

CHAPTERS (by song):
{CHAPTERS}

"The Cabinet of Dr. Caligari" (1920) is in the public domain. This is a non-commercial fan reinterpretation for artistic and educational purposes.

#oldschool #progressiverock #rock #terror #experimental #silentfilm #germanexpressionism #horror #artrock #conceptalbum #1920s #fullmovie #itwastime #thehollowhour #undergroundmusic""",
        "tags": [
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
        ],
    },
    "es": {
        "title": "El gabinete del Dr. Caligari (1920) — Reinterpretada con rock progresivo | It Was Time",
        "description": f""""El gabinete del Dr. Caligari" (1920), la obra cumbre del expresionismo alemán de terror dirigida por Robert Wiene, reinterpretada: se han quitado los rótulos originales en alemán y sustituido por nuevos textos narrativos, y la película lleva de principio a fin la banda sonora de "The Hollow Hour", el álbum debut conceptual de la banda de rock progresivo It Was Time.

Sin diálogos, sin música original — solo las imágenes de la propia película, reestructuradas, con una banda sonora completamente nueva creada para ella.

{LINKS_ES}

CAPÍTULOS (por canción):
{CHAPTERS}

"El gabinete del Dr. Caligari" (1920) es de dominio público. Esta es una reinterpretación de fan sin ánimo de lucro, con fines artísticos y educativos.

#cineclasico #rockprogresivo #rock #terror #experimental #cinemudo #expresionismoaleman #peliculacompleta #oldschool #albumconceptual #itwastime #thehollowhour #musicaexperimental #rockexperimental #peliculaterror1920""",
        "tags": [
            "el gabinete del doctor caligari",
            "cine mudo",
            "expresionismo aleman",
            "pelicula de terror 1920",
            "pelicula de dominio publico",
            "rock progresivo",
            "album conceptual",
            "rock experimental",
            "banda de rock progresivo",
            "pelicula muda con musica",
            "cine clasico de terror",
            "it was time banda",
            "the hollow hour",
            "pelicula completa reinterpretada",
            "cine expresionista aleman",
        ],
    },
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video_path")
    parser.add_argument("--lang", choices=["en", "es"], default="en")
    parser.add_argument("--publish-now", action="store_true", help="Subir directamente como público, en vez de privado para revisar antes")
    parser.add_argument("--publish-date", default=None, help="Fecha de publicación programada, hora de España (ej. 2026-08-07)")
    parser.add_argument("--publish-time", default="20:00", help="Hora de publicación programada, hora de España (por defecto 20:00)")
    parser.add_argument("--channel", default=None, help="Canal de YouTube a usar, si hace falta (ver src/youtube_uploader._token_path_for)")
    args = parser.parse_args()

    if not Path(args.video_path).exists():
        print(f"No encuentro el vídeo: {args.video_path}")
        sys.exit(1)

    if args.publish_now and args.publish_date:
        print("No tiene sentido pedir --publish-now y --publish-date a la vez -- elige uno de los dos.")
        sys.exit(1)

    publish_at = None
    if args.publish_date:
        local_dt = datetime.strptime(
            f"{args.publish_date} {args.publish_time}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=ZoneInfo("Europe/Madrid"))
        publish_at = local_dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")

    meta = METADATA[args.lang]
    privacy_status = "public" if args.publish_now else "private"
    print(f"-> Subiendo como {privacy_status} ({args.lang}): {Path(args.video_path).name}")
    print(f"   Título: {meta['title']}")
    if publish_at:
        print(f"   Programado para publicarse el {args.publish_date} a las {args.publish_time} (hora de España) -> {publish_at} UTC")

    video_id = upload_video(
        video_path=args.video_path,
        title=meta["title"],
        description=meta["description"],
        tags=meta["tags"],
        privacy_status=privacy_status,
        publish_at=publish_at,
        default_language=args.lang,
        channel=args.channel,
    )
    print(f"\n-> Subido: https://youtube.com/watch?v={video_id}")
    if publish_at:
        print(f"   Se publicará solo el {args.publish_date} a las {args.publish_time} (hora de España) -- hasta entonces sigue en privado.")
    elif privacy_status == "private":
        print("   Está en PRIVADO -- revísalo en YouTube Studio y cámbialo a Público cuando estés conforme.")


if __name__ == "__main__":
    main()
