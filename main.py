"""
main.py — Orquestador del pipeline completo.

Uso:
    python main.py --audio input/cancion.mp3 --cover input/portada.jpg \
        --artist "Telvorn" --title "Caminante" --genre "doom-folk / post-rock" \
        --context "Tema sobre..." --shorts 3

Para un LP completo, pásale una carpeta con varias pistas:
    python main.py --album-dir input/mi_lp/ --cover input/portada.jpg \
        --artist "Telvorn" --genre "..." --context "..." --shorts 2
"""

import argparse
import json
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from src.audio_analysis import find_best_moments, find_many_moments
from src.video_analysis import find_best_video_moment
from src.video_generator import generate_main_video
from src.shorts_generator import generate_short
from src.metadata_generator import generate_metadata
from src.lyrics_align import resolve_lyrics_srt
from src.cover_sequence import MOVEMENTS
from src.film_editor import build_energy_driven_edit, render_edit
from src.video_generator import _get_audio_duration as _get_track_duration

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".m4v")
COVER_EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS


def resolve_cover(cover_arg):
    """
    Si `cover_arg` es una carpeta, devuelve la lista ordenada de imágenes
    y/o clips de vídeo que contiene (cada una tendrá su propio movimiento
    de cámara en el vídeo principal, o su movimiento real si ya es un
    clip). Si es un archivo, lo devuelve tal cual.
    """
    path = Path(cover_arg)
    if path.is_dir():
        images = sorted(
            p for p in path.iterdir() if p.suffix.lower() in COVER_EXTENSIONS
        )
        if not images:
            raise ValueError(f"La carpeta {cover_arg} no contiene imágenes ni vídeos (.jpg/.png/.mp4...).")
        return [str(p) for p in images]
    return cover_arg


def _resolve_single_cover(cover_arg):
    """
    Como `resolve_cover`, pero para un sitio que necesita un único archivo
    (los Shorts no admiten una carpeta/lista, solo una portada). Si
    `cover_arg` es una carpeta, se queda con el primer archivo válido de
    dentro en vez de pasar la ruta de la carpeta tal cual (eso rompía la
    generación del Short más adelante, con un error de "no se puede leer
    una carpeta como imagen").
    """
    path = Path(cover_arg)
    if path.is_dir():
        images = sorted(
            p for p in path.iterdir() if p.suffix.lower() in COVER_EXTENSIONS
        )
        if not images:
            raise ValueError(f"La carpeta {cover_arg} no contiene imágenes ni vídeos (.jpg/.png/.mp4...).")
        return str(images[0])
    return cover_arg


def process_track(
    audio_path, cover_path, artist, title, genre, context, n_shorts, out_dir,
    lyrics_path=None, lyrics_offset=0.0, shorts_cover_override=None,
    watermark_logo_light_path=None, watermark_logo_dark_path=None,
    shorts_out_dir=None, shorts_clips=None, shorts_per_clip=3,
    film_edit=None,
):
    """
    `shorts_out_dir`: si se indica, los Shorts se guardan ahí en vez de en
    `out_dir` (para separar vídeos principales y Shorts en carpetas
    distintas, ej. VIDEOS/ y SHORTS/ de un LP). Por defecto, igual que
    siempre: en la misma carpeta que el vídeo principal.

    `shorts_clips`: si se indica (lista de clips de vídeo, ej. los mismos
    que ya se han buscado para el vídeo principal), genera `shorts_per_clip`
    Shorts por cada uno de esos clips —cada uno con su propio mejor momento
    de audio Y su propio mejor momento de vídeo dentro del clip— en vez de
    usar siempre la misma portada para los `n_shorts` Shorts. Sustituye por
    completo a `n_shorts`/`shorts_cover_override` cuando se usa.

    `film_edit`: dict {"film_path", "tagged_scenes", "exclude_ranges"} — si
    se indica, tanto el vídeo principal como los `n_shorts` Shorts se
    montan con cortes reales de esa película (src.film_editor), con la
    duración de cada corte variando según la energía del audio en ese
    tramo. Sustituye por completo a `cover_path`/`shorts_clips`/
    `shorts_cover_override` cuando se usa. `exclude_ranges` es un set
    mutable compartido entre todos los temas del LP para no repetir el
    mismo plano de la película dos veces en todo el álbum.
    """
    title_safe = title.replace(" ", "_")
    out_dir = Path(out_dir) / title_safe
    out_dir.mkdir(parents=True, exist_ok=True)
    shorts_dir = Path(shorts_out_dir) / title_safe if shorts_out_dir else out_dir
    shorts_dir.mkdir(parents=True, exist_ok=True)

    cover = None if film_edit else resolve_cover(cover_path)
    if film_edit:
        cover_for_shorts = None
    elif shorts_clips:
        # el modo "un Short por cada clip descargado" no necesita una
        # portada única para todos los Shorts, así que no hace falta
        # resolver `cover_for_shorts` en absoluto.
        cover_for_shorts = None
    elif shorts_cover_override:
        # portada (imagen o clip) buscada/generada específicamente en
        # orientación vertical para los Shorts, en vez de reutilizar la del
        # vídeo principal (pensada en horizontal).
        cover_for_shorts = _resolve_single_cover(shorts_cover_override)
    elif isinstance(cover, list):
        # sin una portada vertical dedicada: entre las del vídeo principal
        # (pensadas en horizontal), se prefiere una imagen fija a un clip de
        # vídeo para los Shorts, ya que no sabemos si el clip es horizontal
        # o vertical y recortarlo a lo bruto puede quedar peor que la imagen.
        images_only = [c for c in cover if Path(c).suffix.lower() in IMAGE_EXTENSIONS]
        cover_for_shorts = images_only[0] if images_only else cover[0]
    else:
        cover_for_shorts = cover

    print(f"\n=== Procesando: {title} ===")

    if lyrics_path and lyrics_path.lower().endswith(".txt"):
        print("-> Sincronizando la letra con el audio (puede tardar unos minutos)...")
    lyrics_srt, lyrics_is_temp = resolve_lyrics_srt(audio_path, lyrics_path)

    if lyrics_srt and lyrics_is_temp:
        # Guardamos el .srt auto-sincronizado en la carpeta de salida para
        # que se pueda revisar/corregir a mano y reutilizar directamente
        # como .srt (sin volver a pasar por el reconocimiento de voz).
        saved_srt = out_dir / "letra_sincronizada.srt"
        with open(lyrics_srt, encoding="utf-8") as f:
            saved_srt.write_text(f.read(), encoding="utf-8")
        print(f"-> Letra auto-sincronizada guardada en: {saved_srt}")
        print("   Si sale desfasada, ábrela y ajusta a mano los tiempos, o "
              "usa un offset manual.")

    try:
        # 1. Vídeo principal
        print("-> Generando vídeo principal...")
        main_video_path = out_dir / "main_video.mp4"
        track_scene_pool = None
        if film_edit:
            print("   Montando la película (cortes sincronizados a la energía del audio)...")
            total_duration = _get_track_duration(audio_path)
            track_used_scenes = []
            main_film_edit = build_energy_driven_edit(
                audio_path, 0.0, total_duration,
                film_edit["tagged_scenes"], film_edit["exclude_ranges"],
                min_cut=2.0, max_cut=8.0,
                used_scenes_out=track_used_scenes,
                film_path=film_edit["film_path"],
            )
            # los Shorts de este mismo tema reutilizan SOLO estos planos (los
            # que ya salen en su vídeo principal) en vez de seguir gastando
            # planos nuevos del álbum — si no, con 12 temas x (1 vídeo + 3
            # Shorts) el pool de planos distintos de la película se agota
            # enseguida (a partir del 2º-3º tema ya no quedan planos frescos).
            seen_keys = set()
            track_scene_pool = []
            for s in track_used_scenes:
                key = f"{s['start']}-{s['end']}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    track_scene_pool.append(s)
            main_edit_path = tempfile.NamedTemporaryFile(suffix=".mp4", prefix="main_film_edit_", delete=False).name
            render_edit(film_edit["film_path"], main_film_edit, main_edit_path, w=1920, h=1080)
            main_cover = main_edit_path
        else:
            main_cover = cover
        try:
            generate_main_video(
                audio_path, main_cover, str(main_video_path), lyrics_path=lyrics_srt,
                lyrics_offset=lyrics_offset, track_title=title,
            )
        finally:
            # el montaje de la película es solo un paso intermedio (sin
            # audio) para construir main_video.mp4 — no debe quedarse en la
            # carpeta final, es fácil confundirlo con un vídeo roto.
            if film_edit:
                os.remove(main_edit_path)

        print("-> Generando metadatos del vídeo principal...")
        main_meta = generate_metadata(artist, title, genre, context, content_type="main")
        with open(out_dir / "main_video_metadata.json", "w", encoding="utf-8") as f:
            json.dump(main_meta, f, ensure_ascii=False, indent=2)

        # 2. Mejores momentos -> Shorts
        if film_edit:
            print(f"-> Generando {n_shorts} Shorts montados con cortes de la película...")
            moments = find_many_moments(audio_path, n_shorts, clip_duration=22.0)
            # pool local del tema (no el global del álbum): los Shorts de
            # este tema pueden repetir entre sí los planos de su propio
            # vídeo principal sin gastar más planos frescos del álbum.
            track_shorts_exclude = set()
            for i, moment in enumerate(moments[:n_shorts], start=1):
                print(
                    f"-> Montando Short {i}/{n_shorts} "
                    f"(audio {moment['start']:.1f}s-{moment['end']:.1f}s)..."
                )
                short_edit = build_energy_driven_edit(
                    audio_path, moment["start"], moment["end"],
                    track_scene_pool, track_shorts_exclude,
                    film_path=film_edit["film_path"],
                )
                short_edit_path = tempfile.NamedTemporaryFile(
                    suffix=".mp4", prefix="short_film_edit_", delete=False
                ).name
                render_edit(film_edit["film_path"], short_edit, short_edit_path, w=1080, h=1920)

                short_path = shorts_dir / f"short_{i:02d}.mp4"
                try:
                    generate_short(
                        audio_path, short_edit_path, str(short_path), moment["start"], moment["end"],
                        movement=MOVEMENTS[(i - 1) % len(MOVEMENTS)],
                        lyrics_path=lyrics_srt,
                        lyrics_offset=lyrics_offset,
                        track_title=title,
                        watermark_logo_light_path=watermark_logo_light_path,
                        watermark_logo_dark_path=watermark_logo_dark_path,
                        # 1.0s, no 0.0: el montaje empieza con un fundido a negro
                        # (ver src/film_editor.py) — coger el fotograma de
                        # referencia justo en el negro hace que el detector de
                        # personas confunda el negro con "una persona ocupando
                        # todo el encuadre" y tape el Short entero (mismo fallo
                        # que en el vídeo principal, ver _extract_reference_frame).
                        cover_offset=min(1.0, moment["end"] - moment["start"]),
                        hook_text=None if lyrics_srt else title,
                    )
                finally:
                    # igual que en main_video: el montaje es solo un paso
                    # intermedio (sin audio), no debe quedarse en SHORTS.
                    os.remove(short_edit_path)

                short_meta = generate_metadata(artist, title, genre, context, content_type="short")
                with open(shorts_dir / f"short_{i:02d}_metadata.json", "w", encoding="utf-8") as f:
                    json.dump(short_meta, f, ensure_ascii=False, indent=2)
        elif shorts_clips:
            total_shorts = len(shorts_clips) * shorts_per_clip
            print(
                f"-> Generando {total_shorts} Shorts ({shorts_per_clip} por "
                f"cada uno de los {len(shorts_clips)} clips de vídeo)..."
            )
            # 20-35s es el rango con mejor tasa de finalización en Shorts (lo
            # que más pesa para el algoritmo, más que las visitas en bruto);
            # 22s se queda cómodo dentro de ese rango sin arrastrarse.
            moments = find_many_moments(audio_path, total_shorts, clip_duration=22.0)
            short_i = 0
            for clip in shorts_clips:
                for _ in range(shorts_per_clip):
                    moment = moments[short_i % len(moments)] if moments else {"start": 0.0, "end": 22.0}
                    moment_duration = moment["end"] - moment["start"]
                    video_offset = find_best_video_moment(clip, moment_duration)
                    short_i += 1
                    print(
                        f"-> Generando Short {short_i}/{total_shorts} "
                        f"(clip {Path(clip).name}, audio {moment['start']:.1f}s-{moment['end']:.1f}s, "
                        f"vídeo desde {video_offset:.1f}s)..."
                    )
                    short_path = shorts_dir / f"short_{short_i:02d}.mp4"
                    generate_short(
                        audio_path, clip, str(short_path), moment["start"], moment["end"],
                        movement=MOVEMENTS[(short_i - 1) % len(MOVEMENTS)],
                        lyrics_path=lyrics_srt,
                        lyrics_offset=lyrics_offset,
                        track_title=title,
                        watermark_logo_light_path=watermark_logo_light_path,
                        watermark_logo_dark_path=watermark_logo_dark_path,
                        cover_offset=video_offset,
                        hook_text=None if lyrics_srt else title,
                    )

                    short_meta = generate_metadata(artist, title, genre, context, content_type="short")
                    with open(shorts_dir / f"short_{short_i:02d}_metadata.json", "w", encoding="utf-8") as f:
                        json.dump(short_meta, f, ensure_ascii=False, indent=2)
        else:
            print(f"-> Detectando {n_shorts} mejores momentos...")
            moments = find_best_moments(audio_path, top_n=n_shorts)

            for i, moment in enumerate(moments, start=1):
                print(f"-> Generando Short {i} ({moment['start']:.1f}s - {moment['end']:.1f}s)...")
                short_path = shorts_dir / f"short_{i}.mp4"
                generate_short(
                    audio_path, cover_for_shorts, str(short_path), moment["start"], moment["end"],
                    movement=MOVEMENTS[(i - 1) % len(MOVEMENTS)],
                    lyrics_path=lyrics_srt,
                    lyrics_offset=lyrics_offset,
                    track_title=title,
                    watermark_logo_light_path=watermark_logo_light_path,
                    watermark_logo_dark_path=watermark_logo_dark_path,
                    hook_text=None if lyrics_srt else title,
                )

                short_meta = generate_metadata(artist, title, genre, context, content_type="short")
                with open(shorts_dir / f"short_{i}_metadata.json", "w", encoding="utf-8") as f:
                    json.dump(short_meta, f, ensure_ascii=False, indent=2)
    finally:
        if lyrics_is_temp:
            os.remove(lyrics_srt)

    print(f"=== Listo: vídeo en {out_dir}, Shorts en {shorts_dir} ===")
    return out_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", help="Ruta a un único archivo de audio")
    parser.add_argument("--album-dir", help="Carpeta con varias pistas para procesar como LP")
    parser.add_argument(
        "--cover",
        required=True,
        help=(
            "Ruta a la imagen de portada, o a una carpeta con varias "
            "imágenes (cada una tendrá su propio movimiento de cámara "
            "en el vídeo principal)"
        ),
    )
    parser.add_argument("--artist", required=True)
    parser.add_argument("--title", help="Título del tema (obligatorio si usas --audio)")
    parser.add_argument("--genre", required=True)
    parser.add_argument("--context", required=True, help="Contexto/concepto artístico")
    parser.add_argument("--shorts", type=int, default=3, help="Número de shorts a generar por tema")
    parser.add_argument("--out", default="output", help="Carpeta de salida")
    parser.add_argument(
        "--lyrics",
        help=(
            "Letra para superponer en el vídeo principal: un .srt ya "
            "sincronizado, o un .txt en texto plano (una frase por línea) "
            "para sincronizarlo automáticamente contra el audio"
        ),
    )
    parser.add_argument(
        "--lyrics-offset",
        type=float,
        default=0.0,
        help=(
            "Ajuste manual en segundos de la letra (positivo = retrasa, "
            "negativo = adelanta). Útil si el reconocimiento automático "
            "la deja algo desfasada. Ej: -3 si sale 3s tarde."
        ),
    )
    parser.add_argument(
        "--watermark-logo-light",
        help=(
            "Ruta a la variante CLARA del logo (PNG con fondo transparente), "
            "para quemarla junto al nombre del tema en la esquina superior "
            "izquierda de los Shorts cuando el fondo del vídeo en esa zona "
            "sea oscuro. El vídeo principal lleva solo el nombre del tema; "
            "el logo ahí lo pone el watermark de canal de YouTube, ver "
            "configurar_marca_agua.py). Opcional."
        ),
    )
    parser.add_argument(
        "--watermark-logo-dark",
        help=(
            "Ruta a la variante OSCURA del logo, para cuando el fondo del "
            "vídeo en la esquina superior izquierda sea claro. Si solo das "
            "una de las dos variantes, se usa siempre esa. Opcional."
        ),
    )
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        parser.error(
            "Falta ANTHROPIC_API_KEY. Copia .env.example a .env y añade tu "
            "clave (ANTHROPIC_API_KEY=sk-ant-...) antes de ejecutar."
        )

    if args.audio:
        if not args.title:
            parser.error("--title es obligatorio cuando usas --audio")
        process_track(
            args.audio, args.cover, args.artist, args.title,
            args.genre, args.context, args.shorts, args.out,
            lyrics_path=args.lyrics, lyrics_offset=args.lyrics_offset,
            watermark_logo_light_path=args.watermark_logo_light,
            watermark_logo_dark_path=args.watermark_logo_dark,
        )
    elif args.album_dir:
        tracks = sorted(Path(args.album_dir).glob("*.mp3")) + sorted(Path(args.album_dir).glob("*.wav"))
        for track_path in tracks:
            track_title = track_path.stem
            process_track(
                str(track_path), args.cover, args.artist, track_title,
                args.genre, args.context, args.shorts, args.out,
                lyrics_offset=args.lyrics_offset,
                watermark_logo_light_path=args.watermark_logo_light,
                watermark_logo_dark_path=args.watermark_logo_dark,
            )
    else:
        parser.error("Debes indicar --audio o --album-dir")


if __name__ == "__main__":
    main()
