"""
procesar_lp.py — "app" para automatizar un LP completo de una vez.

Arrastra sobre el icono (o un acceso directo a `procesar_lp.bat`) la
carpeta con los audios del LP y el documento del LP en .txt (letras,
estilo, concepto — en texto libre, como se lo describirías a alguien; no
hace falta ninguna plantilla fija). Si no arrastras nada, te pregunta las
rutas.

Te pregunta UNA vez al principio (artista/género, masterización, marca de
agua, número de Shorts...) y a partir de ahí genera solo, uno detrás de
otro, el vídeo principal + Shorts + metadatos de cada tema del LP, con
todo lo que ya tiene el pipeline (masterización, normalización de
volumen, portadas/vídeo de stock, letra karaoke, marca de agua, acabado
cinematográfico...). Al final, si quieres, encadena también la
programación/subida a YouTube de todos los temas (usando el calendario de
lanzamiento del LP que ya hayáis calculado con calendario_lp.py).

Uso:
    python procesar_lp.py [carpeta_audios] [documento_lp.txt]
"""

import json
import os
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

if not os.environ.get("ANTHROPIC_API_KEY"):
    print(
        "Falta ANTHROPIC_API_KEY. Copia .env.example a .env y añade tu "
        "clave (ANTHROPIC_API_KEY=sk-ant-...) antes de continuar."
    )
    sys.exit(1)

import subir_tema as st
from main import process_track
from src.lp_dossier import parse_lp_dossier

AUDIO_EXTENSIONS = st.AUDIO_EXTENSIONS


def _resolve_dropped_paths(args):
    """
    De los argumentos recibidos (arrastrados sobre el icono, en cualquier
    orden), identifica cuál es la carpeta de audios y cuál el documento
    del LP (.txt). Si no encaja exactamente uno de cada, devuelve
    (None, None) para que el que llama pida las rutas a mano.
    """
    folder = None
    dossier = None
    for arg in args:
        p = Path(arg.strip('"'))
        if p.is_dir():
            folder = str(p)
        elif p.is_file() and p.suffix.lower() == ".txt":
            dossier = str(p)
    return folder, dossier


def _natural_sort_key(path):
    m = re.match(r"^\D*(\d+)", Path(path).stem)
    return (int(m.group(1)), Path(path).stem) if m else (10**9, Path(path).stem)


def _find_audio_files(folder):
    return sorted(
        (p for p in Path(folder).rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS),
        key=_natural_sort_key,
    )


def _prepare_audio(audio_path, reference_path):
    from src.mastering import master_audio
    from src.audio_hygiene import trim_silence, check_mono_compatibility, denoise_if_needed
    from src.loudness import normalize_loudness, TARGET_I

    if reference_path:
        mastered_dir = Path("mastered")
        mastered_dir.mkdir(exist_ok=True)
        out_path = str(mastered_dir / f"{Path(audio_path).stem}_mastered.wav")
        print("   Masterizando con Matchering...")
        audio_path = master_audio(audio_path, reference_path, out_path)

    prepared_dir = Path("prepared")
    prepared_dir.mkdir(exist_ok=True)

    trimmed = str(prepared_dir / f"{Path(audio_path).stem}_trimmed.wav")
    audio_path = trim_silence(audio_path, trimmed)

    mono_check = check_mono_compatibility(audio_path)
    if mono_check.get("warning"):
        print(
            f"   Aviso: la mezcla pierde {abs(mono_check['diff_db']):.1f} dB al "
            "sumarse a mono (posible cancelación de fase)."
        )

    denoised = str(prepared_dir / f"{Path(audio_path).stem}_denoised.wav")
    audio_path, applied, floor_db = denoise_if_needed(audio_path, denoised)
    if applied:
        print(f"   Ruido de fondo detectado (suelo ~{floor_db:.0f}dB) — reducción suave aplicada.")

    normalized_dir = Path("normalized")
    normalized_dir.mkdir(exist_ok=True)
    final_path = str(normalized_dir / f"{Path(audio_path).stem}_normalized.wav")
    print(f"   Normalizando a {TARGET_I} LUFS...")
    return normalize_loudness(audio_path, final_path)


def _generate_ai_cover(artist, title, genre, context, n_images=3):
    from src.image_prompts import generate_image_prompts
    from src.image_generator import generate_cover_images

    prompts = generate_image_prompts(artist, title, genre, context, n_images=n_images)
    cover_dir = Path("input") / title.replace(" ", "_")
    generate_cover_images(prompts, str(cover_dir))
    return str(cover_dir)


def _resolve_cover_unattended(artist, title, genre, context, audio_path, have_openai, have_stock):
    if have_stock:
        n_images = st._suggest_clip_count(audio_path)
        cover = st._resolve_stock_video_covers(
            artist, title, genre, context, n_images, have_openai,
            orientation="landscape", min_duration=8.0, homogenize=True,
        )
        if cover is None and have_openai:
            cover = _generate_ai_cover(artist, title, genre, context)
        shorts_cover = st._resolve_stock_video_covers(
            artist, title, genre, context, 1, have_openai, orientation="portrait",
        )
        return cover, shorts_cover

    if have_openai:
        return _generate_ai_cover(artist, title, genre, context), None

    return None, None


def _leading_number(text):
    m = re.match(r"^(\d+)", text)
    return int(m.group(1)) if m else None


def _run_youtube_phase(track_out_dirs, calendar_path):
    with open(calendar_path, encoding="utf-8") as f:
        lp_calendar = json.load(f)

    idioma = st.ask(
        "Idioma principal del contenido (es/en...; Enter para no indicarlo)", required=False,
    )
    thumb_template = st.ask_path(
        "Ruta a una plantilla de miniatura (portada del LP con el logo; "
        "Enter para usar un fotograma del vídeo)", required=False,
    )
    playlist_name = st.ask(
        "Nombre de la lista de reproducción del LP (Enter para no usar ninguna)", required=False,
    )
    extra_links = st.ask(
        "Enlaces extra para la descripción (redes, web...; Enter para ninguno)", required=False,
    )
    interval_days = int(st.ask(
        "Días entre el vídeo principal y cada Short dentro de un mismo tema", "3",
    ))
    hora_raw = st.ask("Hora de publicación (hora de España, HH:MM) para todos los envíos", "18:00")
    hh, mm = (int(x) for x in hora_raw.split(":"))

    from src.release_calendar import build_schedule, save_schedule
    from src.youtube_batch import upload_schedule

    schedules = []
    for out_dir in track_out_dirs:
        track_title = Path(out_dir).name.replace("_", " ")
        track_number = _leading_number(track_title)
        cal_entry = next(
            (c for c in lp_calendar if _leading_number(c["track"]) == track_number),
            None,
        )
        if not cal_entry:
            print(f"  Aviso: no encuentro '{track_title}' en el calendario del LP, salto su programación.")
            continue
        youtube_start = date.fromisoformat(cal_entry["youtube_start_date"])
        schedule = build_schedule(out_dir, youtube_start, hh, mm, interval_days=interval_days)
        save_schedule(schedule, out_dir)
        schedules.append((out_dir, schedule, track_title, track_number))

    print("\n--- Calendario propuesto para todo el LP ---")
    for out_dir, schedule, track_title, _ in schedules:
        print(f"\n{track_title}:")
        for item in schedule:
            print(f"  [{item['kind']:5}] {item['publish_at_local']}  ->  {Path(item['video_path']).name}")

    confirmar = st.ask("\n¿Subir y programar TODO esto en YouTube ahora? [s/N]", "n").lower()
    if not confirmar.startswith("s"):
        print("No se ha subido nada. Puedes relanzar esta fase más tarde.")
        return

    youtube = None
    playlist_id = None
    link_block = ""
    if playlist_name:
        from src.youtube_uploader import get_authenticated_service
        from src.youtube_playlists import create_or_get_playlist, playlist_url
        youtube = get_authenticated_service()
        playlist_id = create_or_get_playlist(youtube, playlist_name)
        print(f"-> Lista de reproducción: {playlist_url(playlist_id)}")
        link_block += f"\n\n▶ Escucha todo el álbum: {playlist_url(playlist_id)}"
    if extra_links:
        link_block += f"\n\n{extra_links}"

    for out_dir, schedule, track_title, track_number in schedules:
        track_position = track_number - 1 if track_number is not None else None
        upload_schedule(
            out_dir, schedule, thumb_template=thumb_template, playlist_id=playlist_id,
            youtube=youtube, link_block=link_block, idioma=idioma, track_position=track_position,
        )

    print("\nListo. Todos los temas del LP están subidos (ocultos) y se publicarán solos en sus fechas.")


def main():
    print("=== Telvorn Automation — procesar LP completo ===\n")

    folder, dossier_path = _resolve_dropped_paths(sys.argv[1:])
    if not folder:
        folder = st.ask("Ruta a la carpeta con los audios del LP")
    if not dossier_path:
        dossier_path = st.ask_path("Ruta al documento del LP (.txt)")

    if not Path(folder).is_dir():
        print(f"No encuentro la carpeta: {folder}")
        sys.exit(1)

    audio_files = _find_audio_files(folder)
    if not audio_files:
        print(f"No encuentro ningún .mp3/.wav en {folder}.")
        sys.exit(1)

    print(f"-> Leyendo el documento del LP y extrayendo los temas (puede tardar un minuto)...")
    with open(dossier_path, encoding="utf-8") as f:
        dossier_text = f.read()
    dossier = parse_lp_dossier(dossier_text)
    tracks = sorted(dossier["tracks"], key=lambda t: t["number"])

    print(f"\nEncontrados {len(audio_files)} audios en la carpeta, {len(tracks)} temas en el documento.")
    if len(audio_files) != len(tracks):
        print("Aviso: el número de audios y de temas del documento NO coincide:")
        for f in audio_files:
            print(f"   audio: {f.name}")
        for t in tracks:
            print(f"   documento: {t['number']}. {t['title']}")
        continuar = st.ask(
            "¿Continuar emparejando por orden hasta donde lleguen (puede "
            "descuadrar temas)? [s/N]", "n",
        ).lower()
        if not continuar.startswith("s"):
            print("Nada generado. Ajusta la carpeta o el documento y vuelve a intentarlo.")
            sys.exit(1)

    pairs = list(zip(audio_files, tracks))

    print("\n--- Datos generales detectados ---")
    memory = st._load_memory()
    artist = st.ask("Artista", dossier.get("artist"))
    lp_title = st.ask("Nombre del LP", dossier.get("lp_title"))
    genre = st.ask("Género/estilo", dossier.get("genre"))
    memory.update({"artist": artist, "genre": genre})

    do_master = st.ask(
        "¿Masterizar todos los temas contra una misma canción de referencia? [s/N]", "n",
    ).lower()
    reference_path = None
    if do_master.startswith("s"):
        reference_path = st.ask_path(
            "Ruta a la canción de referencia (mp3/wav)", default=memory.get("reference_track"),
        )
        memory["reference_track"] = reference_path

    watermark_logo_light = st.ask_path(
        "Ruta al logo CLARO para la marca de agua de los Shorts (PNG "
        "transparente, opcional, Enter para omitir)",
        required=False, default=memory.get("watermark_logo_light"),
    )
    watermark_logo_dark = st.ask_path(
        "Ruta al logo OSCURO (opcional, Enter para omitir)",
        required=False, default=memory.get("watermark_logo_dark"),
    )
    memory["watermark_logo_light"] = watermark_logo_light
    memory["watermark_logo_dark"] = watermark_logo_dark
    st._save_memory(memory)

    n_shorts = int(st.ask("Número de Shorts a generar por tema", "3"))

    have_openai = bool(os.environ.get("OPENAI_API_KEY"))
    have_stock = bool(
        os.environ.get("PEXELS_API_KEY") or os.environ.get("PIXABAY_API_KEY")
        or os.environ.get("COVERR_API_KEY")
    )
    if not have_openai and not have_stock:
        print(
            "  Aviso: no tienes OPENAI_API_KEY ni PEXELS_API_KEY/PIXABAY_API_KEY/"
            "COVERR_API_KEY en tu .env — no podré generar portadas para "
            "ningún tema. Añade alguna clave antes de continuar."
        )
        sys.exit(1)

    print(f"\n=== Empezando: {len(pairs)} temas de \"{lp_title}\" ===\n")

    out_dirs = []
    fallos = []
    for audio_path, track in pairs:
        track_title = f"{track['number']}. {track['title']}"
        print(f"\n--- Tema {track['number']}: {track['title']} ---")
        try:
            prepared_audio = _prepare_audio(str(audio_path), reference_path)

            cover, shorts_cover = _resolve_cover_unattended(
                artist, track_title, genre, track["context"], prepared_audio, have_openai, have_stock,
            )
            if cover is None:
                raise RuntimeError("no se ha podido conseguir ninguna portada/vídeo para este tema")

            lyrics_path = None
            if track.get("lyrics"):
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", prefix="lp_lyrics_", delete=False, encoding="utf-8",
                )
                tmp.write(track["lyrics"])
                tmp.close()
                lyrics_path = tmp.name

            try:
                out_dir = process_track(
                    prepared_audio, cover, artist, track_title, genre, track["context"],
                    n_shorts, "output", lyrics_path=lyrics_path,
                    shorts_cover_override=shorts_cover,
                    watermark_logo_light_path=watermark_logo_light,
                    watermark_logo_dark_path=watermark_logo_dark,
                )
            finally:
                if lyrics_path:
                    os.remove(lyrics_path)

            out_dirs.append(str(out_dir))
        except Exception as e:
            print(f"  ERROR en el tema {track['number']} ({track['title']}): {e}")
            print("  Sigo con el siguiente tema.")
            fallos.append(f"{track['number']}. {track['title']}: {e}")

    print(f"\n=== LP procesado: {len(out_dirs)}/{len(pairs)} temas generados en output/ ===")
    if fallos:
        print("Temas que fallaron:")
        for f in fallos:
            print(f"   - {f}")

    if not out_dirs:
        return

    seguir_youtube = st.ask(
        "\n¿Continuar con la programación/subida a YouTube de todo el LP? [s/N]", "n",
    ).lower()
    if not seguir_youtube.startswith("s"):
        print("Listo por ahora. Puedes programar YouTube más tarde con programar_youtube.py "
              "(tema a tema) o relanzando esta fase.")
        return

    calendar_path = st.ask_path(
        "Ruta al calendario de lanzamiento del LP (calendario_lanzamiento.json, "
        "generado con calendario_lp.py)",
    )
    _run_youtube_phase(out_dirs, calendar_path)


if __name__ == "__main__":
    main()
