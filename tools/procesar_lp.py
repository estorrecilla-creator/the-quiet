"""
procesar_lp.py — "app" para automatizar un LP completo de una vez.

Antes de arrancarlo, copia dentro de `MUSICA/<Grupo>/<NombreDelLP>/` (crea
las carpetas si no existen) el .zip (o carpeta) con los audios del LP y el
documento del LP en .txt (letras, estilo, concepto — en texto libre, como
se lo describirías a alguien; no hace falta ninguna plantilla fija). El
programa te pregunta el grupo y el LP (mostrándote los que ya existen) y
coge solo de ahí todo lo que necesita — no hace falta arrastrar nada.

Te pregunta UNA vez al principio (artista/género, masterización, marca de
agua, miniatura, calendario de lanzamiento con los primeros singles...) y a
partir de ahí genera solo, uno detrás de otro, el vídeo principal + Shorts
+ metadatos de cada tema del LP, con todo lo que ya tiene el pipeline
(masterización, normalización de volumen, 15 clips de vídeo libre de
derechos sin repetirse en todo el LP + 3 Shorts por clip con su propio
mejor momento de audio y de vídeo, letra karaoke, marca de agua, acabado
cinematográfico...). El audio final queda listo para DistroKid en
`AUDIO_FINAL/`, los vídeos en `VIDEOS/`, los Shorts en `SHORTS/` y las
miniaturas en `MINIATURAS/`, todo dentro de la carpeta del LP. Al final, si
quieres, encadena también la programación/subida a YouTube de todo el LP
(vídeos principales + los Shorts, todos programados de golpe con su fecha
de publicación ya fijada, según el calendario de lanzamiento).

Uso:
    python tools/procesar_lp.py
"""

import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

if not os.environ.get("ANTHROPIC_API_KEY"):
    print(
        "Falta ANTHROPIC_API_KEY. Copia .env.example a .env y añade tu "
        "clave (ANTHROPIC_API_KEY=sk-ant-...) antes de continuar."
    )
    sys.exit(1)

import subir_tema as st
from main import process_track, resolve_cover, VIDEO_EXTENSIONS
from src.lp_dossier import parse_lp_dossier
from src.thumbnail_template import make_track_thumbnail

AUDIO_EXTENSIONS = st.AUDIO_EXTENSIONS
MUSICA_DIR = REPO_ROOT / "MUSICA"
OUTPUT_SUBFOLDERS = {"AUDIO_FINAL", "VIDEOS", "SHORTS", "MINIATURAS"}
N_CLIPS_PER_TRACK = 15  # Pendiente #4: fijo, no variable con la duración
SHORTS_PER_CLIP = 3     # Pendiente #6: 3 Shorts por cada uno de los 15 clips (45/tema)
FALLBACK_N_SHORTS = 3   # solo si no hay ningún clip de vídeo (portada de imagen fija)


# --------------------------------------------------------------------
# Pendiente #1: descubrir grupo/LP dentro de MUSICA/ en vez de arrastrar
# --------------------------------------------------------------------

def _list_subdirs(path):
    if not path.is_dir():
        return []
    return sorted(p.name for p in path.iterdir() if p.is_dir())


def _ask_from_list(prompt, options, what):
    if options:
        print(f"  {what} ya existentes: {', '.join(options)}")
    else:
        print(f"  Todavía no hay ninguna carpeta de {what.lower()}.")
    while True:
        value = st.ask(prompt)
        match = next((o for o in options if o.lower() == value.lower()), None)
        if match:
            return match
        if not options:
            return value
        print(f"  No encuentro \"{value}\" entre: {', '.join(options)}. Comprueba el nombre exacto de la carpeta.")


def _find_lp_source(lp_dir: Path):
    """
    Dentro de la carpeta del LP: el .zip (o carpeta) con los audios "en
    bruto" y el documento .txt — ignorando las subcarpetas que genera el
    propio pipeline (AUDIO_FINAL, VIDEOS, SHORTS, MINIATURAS), para poder
    relanzar sin que se confundan con la fuente original.
    """
    dossiers = list(lp_dir.glob("*.txt"))
    if not dossiers:
        raise RuntimeError(f"No encuentro ningún documento .txt del LP en {lp_dir}")
    if len(dossiers) > 1:
        print(f"  Aviso: hay varios .txt en {lp_dir}, uso el primero: {dossiers[0].name}")
    dossier_path = str(dossiers[0])

    zips = list(lp_dir.glob("*.zip"))
    if zips:
        if len(zips) > 1:
            print(f"  Aviso: hay varios .zip en {lp_dir}, uso el primero: {zips[0].name}")
        return str(zips[0]), dossier_path

    candidate_dirs = [p for p in lp_dir.iterdir() if p.is_dir() and p.name not in OUTPUT_SUBFOLDERS]
    if not candidate_dirs:
        raise RuntimeError(f"No encuentro ningún .zip ni carpeta con los audios del LP en {lp_dir}")
    return str(candidate_dirs[0]), dossier_path


def _discover_lp():
    print(f"=== Buscando en {MUSICA_DIR.relative_to(REPO_ROOT)}/ ===\n")
    MUSICA_DIR.mkdir(exist_ok=True)
    groups = _list_subdirs(MUSICA_DIR)
    grupo = _ask_from_list("Nombre del grupo/artista", groups, "Grupos")
    group_dir = MUSICA_DIR / grupo
    lps = _list_subdirs(group_dir)
    lp_name = _ask_from_list("Nombre del LP", lps, "LPs de este grupo")
    lp_dir = group_dir / lp_name
    if not lp_dir.is_dir():
        raise RuntimeError(
            f"No encuentro la carpeta {lp_dir}. Créala y copia dentro el .zip/carpeta "
            "de audios y el documento .txt del LP antes de continuar."
        )
    folder, dossier_path = _find_lp_source(lp_dir)
    return lp_dir, grupo, lp_name, folder, dossier_path


def _extract_zip_if_needed(folder_path: str) -> str:
    p = Path(folder_path)
    if not (p.is_file() and p.suffix.lower() == ".zip"):
        return folder_path
    extract_dir = p.with_suffix("")
    if extract_dir.exists() and any(extract_dir.iterdir()):
        return str(extract_dir)
    print(f"-> Descomprimiendo {p.name}...")
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(p) as zf:
        zf.extractall(extract_dir)
    return str(extract_dir)


def _natural_sort_key(path):
    m = re.match(r"^\D*(\d+)", Path(path).stem)
    return (int(m.group(1)), Path(path).stem) if m else (10**9, Path(path).stem)


def _find_audio_files(folder):
    return sorted(
        (p for p in Path(folder).rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS),
        key=_natural_sort_key,
    )


def _track_display_title(track):
    return f"{track['number']}. {track['title']}"


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename(text: str) -> str:
    """
    Quita los caracteres que Windows no permite en nombres de archivo
    (: / \\ ? * " < > |) sin tocar el resto del texto — para que el
    nombre del archivo de audio final siga siendo reconocible como el
    título real del tema, en vez de fallar al guardarlo o quedar con un
    nombre distinto al del tema.
    """
    text = _INVALID_FILENAME_CHARS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------
# Masterización con distinta canción de referencia según el tema
# --------------------------------------------------------------------

_REFERENCE_EXTENSIONS = (".wav", ".mp3")
_REFERENCE_TEMA_RE = re.compile(r"referencia_tema([\d_\-]+)$", re.IGNORECASE)


def _parse_reference_track_numbers(stem: str):
    m = _REFERENCE_TEMA_RE.match(stem)
    if not m:
        return []
    return [int(n) for n in re.findall(r"\d+", m.group(1))]


def _discover_track_references(lp_dir):
    """
    Busca en la carpeta del LP archivos de referencia de mastering con
    este convenio de nombres:
      - referencia_base.wav (o .mp3)   -> por defecto, para cualquier
        tema que no tenga una referencia propia más específica.
      - referencia_temaN.wav           -> solo para el tema N.
      - referencia_temaN_M.wav         -> para los temas N y M (tantos
        números separados por "_" o "-" como haga falta).
    Devuelve (ruta_base_o_None, {número_de_tema: ruta}).
    """
    base = None
    overrides = {}
    candidates = [
        p for ext in _REFERENCE_EXTENSIONS
        for p in Path(lp_dir).glob(f"referencia*{ext}")
    ]
    for p in sorted(candidates):
        stem = p.stem.lower()
        if stem in ("referencia_base", "referencia"):
            base = str(p)
            continue
        for tn in _parse_reference_track_numbers(stem):
            overrides[tn] = str(p)
    return base, overrides


def _match_track(raw, tracks):
    raw = raw.strip()
    if raw.isdigit():
        n = int(raw)
        return next((t for t in tracks if t["number"] == n), None)
    raw_lower = raw.lower()
    exact = next((t for t in tracks if t["title"].lower() == raw_lower), None)
    if exact:
        return exact
    return next((t for t in tracks if raw_lower in t["title"].lower()), None)


# --------------------------------------------------------------------
# Pendiente #2: calendario de lanzamiento inline (singles + álbum completo)
# --------------------------------------------------------------------

def _ask_release_calendar(tracks, lp_dir):
    from src.lp_release_calendar import build_lp_calendar_custom, save_lp_calendar, next_friday

    print("\n--- Calendario de lanzamiento ---")
    print("Temas del LP:")
    for t in tracks:
        print(f"  {t['number']}. {t['title']}")

    print(
        "\n¿Cuáles son los 4 primeros lanzamientos (singles), en el orden en "
        "que saldrán? Los demás temas se publicarán juntos, como álbum "
        "completo, después del último single."
    )
    singles = []
    for i in range(1, 5):
        while True:
            raw = st.ask(f"  Single {i} (número o título del tema)")
            match = _match_track(raw, tracks)
            if match and match["number"] not in [s["number"] for s in singles]:
                singles.append(match)
                break
            print("  No lo encuentro entre los temas del LP (o ya lo has usado). Prueba otra vez.")

    first_release_raw = st.ask("Fecha del primer single (dd/mm/aaaa)")
    first_release_date = datetime.strptime(first_release_raw, "%d/%m/%Y").date()
    cadence = int(st.ask(
        "Días entre cada single (y entre el último single y el álbum completo)", "14"
    ))
    lead = int(st.ask(
        "Días de antelación para subir cada lanzamiento a DistroKid", "30"
    ))

    release_date = next_friday(first_release_date)
    if release_date != first_release_date:
        print(f"  (Ajustada al viernes siguiente: {release_date.strftime('%d/%m/%Y')} — mejor para listas editoriales)")

    entries = []
    for s in singles:
        entries.append({"track": _track_display_title(s), "distrokid_release_date": release_date})
        release_date = release_date + timedelta(days=cadence)

    album_release_date = release_date
    single_numbers = {s["number"] for s in singles}
    for t in tracks:
        if t["number"] not in single_numbers:
            entries.append({"track": _track_display_title(t), "distrokid_release_date": album_release_date})

    lp_calendar = build_lp_calendar_custom(entries, distrokid_lead_days=lead)

    print("\n--- Calendario propuesto ---")
    for item in lp_calendar:
        print(f"  {item['track']}")
        print(f"      Subir a DistroKid antes de: {item['distrokid_submit_by']}")
        print(f"      Lanzamiento en streaming:   {item['distrokid_release_date']}")

    calendar_path = save_lp_calendar(lp_calendar, lp_dir / "calendario_lanzamiento.json")
    print(f"\nCalendario guardado en: {calendar_path}")
    return lp_calendar


# --------------------------------------------------------------------
# Pendiente #3 + #9: audio final (DistroKid) y miniatura por tema
# --------------------------------------------------------------------

def _prepare_audio(
    audio_path, reference_path, *, title, artist, album=None, genre=None,
    track_number=None, total_tracks=None, final_dir,
):
    from src.mastering import master_audio
    from src.audio_hygiene import trim_silence, check_mono_compatibility, denoise_if_needed
    from src.loudness import normalize_loudness, TARGET_I
    from src.metadata_cleaner import clean_audio_metadata

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
    scratch_path = str(normalized_dir / f"{Path(audio_path).stem}_normalized.wav")
    print(f"   Normalizando a {TARGET_I} LUFS...")
    scratch_path = normalize_loudness(audio_path, scratch_path)

    safe_title = _safe_filename(title)
    final_name = f"{track_number:02d} - {safe_title}.wav" if track_number else f"{safe_title}.wav"
    dest = Path(final_dir) / final_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(scratch_path, dest)

    print("   Limpiando metadatos (fuera cualquier rastro de la herramienta usada para componerlo)...")
    year = date.today().year
    publisher = os.environ.get("RELEASE_PUBLISHER", artist)
    copyright_holder = os.environ.get("RELEASE_COPYRIGHT_HOLDER", artist)
    clean_audio_metadata(
        str(dest), title=title, artist=artist, album=album, album_artist=artist, genre=genre,
        year=year, track_number=track_number, total_tracks=total_tracks,
        composer=artist, lyricist=artist, producer=publisher, publisher=publisher,
        copyright_text=f"© {year} {copyright_holder}",
        phonographic_copyright=f"℗ {year} {copyright_holder}",
    )
    print(f"   Audio final (listo para DistroKid): {dest}")
    return str(dest)


# --------------------------------------------------------------------
# Pendiente #4 + #5: 15 clips fijos por tema, sin repetir en todo el LP
# --------------------------------------------------------------------

def _generate_ai_cover(artist, title, genre, context, n_images=3):
    from src.image_prompts import generate_image_prompts
    from src.image_generator import generate_cover_images
    prompts = generate_image_prompts(artist, title, genre, context, n_images=n_images)
    cover_dir = Path("input") / title.replace(" ", "_")
    generate_cover_images(prompts, str(cover_dir))
    return str(cover_dir)


def _resolve_cover_unattended(artist, title, genre, context, have_openai, have_stock, exclude_urls):
    if have_stock:
        cover = st._resolve_stock_video_covers(
            artist, title, genre, context, N_CLIPS_PER_TRACK, have_openai,
            orientation="landscape", min_duration=8.0, homogenize=True,
            exclude_urls=exclude_urls,
        )
        if cover is None and have_openai:
            cover = _generate_ai_cover(artist, title, genre, context)
        return cover
    if have_openai:
        return _generate_ai_cover(artist, title, genre, context)
    return None


# --------------------------------------------------------------------
# Pendiente #8: recoger lo generado y programar el calendario completo
# --------------------------------------------------------------------

def _collect_track_outputs(tracks, videos_dir, shorts_dir_root):
    result = []
    for t in tracks:
        safe = _track_display_title(t).replace(" ", "_")
        main_video = Path(videos_dir) / safe / "main_video.mp4"
        main_meta = Path(videos_dir) / safe / "main_video_metadata.json"
        if not (main_video.exists() and main_meta.exists()):
            continue
        shorts_track_dir = Path(shorts_dir_root) / safe
        shorts_videos = sorted(
            shorts_track_dir.glob("short_*.mp4"),
            key=lambda p: int("".join(c for c in p.stem if c.isdigit()) or 0),
        )
        shorts = []
        for sv in shorts_videos:
            meta = shorts_track_dir / f"{sv.stem}_metadata.json"
            if meta.exists():
                shorts.append((str(sv), str(meta)))
        result.append({
            "number": t["number"], "title": t["title"],
            "main_video": str(main_video), "main_meta": str(main_meta),
            "shorts": shorts,
        })
    return result


def _run_youtube_phase(
    tracks, videos_dir, shorts_dir_root, lp_calendar, thumbnails, lp_dir,
    artist, lp_title, genre, concept,
):
    from src.lp_shorts_schedule import build_lp_schedule, save_lp_schedule, upload_lp_schedule

    track_outputs = _collect_track_outputs(tracks, videos_dir, shorts_dir_root)
    if not track_outputs:
        print("No hay ningún tema generado, no hay nada que programar.")
        return

    idioma = st.ask("Idioma principal del contenido (es/en...; Enter para no indicarlo)", required=False)
    playlist_name = st.ask("Nombre de la lista de reproducción del LP (Enter para no usar ninguna)", required=False)
    extra_links = st.ask("Enlaces extra para la descripción (redes, web...; Enter para ninguno)", required=False)
    main_hora_raw = st.ask("Hora de publicación del vídeo principal de cada tema (hora de España, HH:MM)", "18:00")
    main_hh, main_mm = (int(x) for x in main_hora_raw.split(":"))

    print("\n-> Calculando el calendario completo del LP (vídeos + Shorts a 12:00 y 21:00)...")
    schedule = build_lp_schedule(track_outputs, lp_calendar, main_hour=main_hh, main_minute=main_mm)

    mains = [i for i in schedule if i["kind"] == "main"]
    shorts_count = len(schedule) - len(mains)
    print("\n--- Calendario propuesto para todo el LP ---")
    print(f"{len(mains)} vídeos principales, {shorts_count} Shorts.")
    print(f"Primer envío: {schedule[0]['publish_at_local']}")
    print(f"Último envío: {schedule[-1]['publish_at_local']}")
    print("\nVídeos principales:")
    for item in mains:
        print(f"  [{item['publish_at_local']}]  {Path(item['video_path']).name}")

    print(
        "\n(Aviso: la cuota gratuita de la API de YouTube solo da para unos 5-6 "
        "vídeos subidos al día, muy por debajo de los que tiene un LP entero — "
        "esto puede tardar varios días/meses en terminar. Una vez confirmes, "
        "queda todo listo para que el resto se suba SOLO cada día con la Tarea "
        "Programada de Windows — no hace falta que relances nada a mano.)"
    )
    confirmar = st.ask("\n¿Subir y programar TODO esto en YouTube ahora? [s/N]", "n").lower()
    save_path = lp_dir / "calendario_youtube.json"
    if not confirmar.startswith("s"):
        save_lp_schedule(schedule, save_path)
        print(f"No se ha subido nada. Calendario guardado en {save_path} — puedes revisarlo y relanzar esta fase más tarde.")
        return

    youtube = None
    playlist_id = None
    link_block = ""
    track_positions = {t["number"]: t["number"] - 1 for t in tracks}
    if playlist_name:
        from src.youtube_uploader import get_authenticated_service
        from src.youtube_playlists import create_or_get_playlist, playlist_url
        from src.youtube_sections import add_playlist_to_section
        from src.metadata_generator import generate_playlist_metadata
        from src.discografia import register_and_link_lp_playlist
        youtube = get_authenticated_service()
        playlist_id = create_or_get_playlist(youtube, playlist_name)
        print(f"-> Lista de reproducción: {playlist_url(playlist_id)}")
        link_block += f"\n\n▶ Escucha todo el álbum: {playlist_url(playlist_id)}"
        add_playlist_to_section(youtube, playlist_id, section_title="Álbumes")
        print('-> Añadida a la sección "Álbumes" de la página de inicio del canal.')

        print("-> Generando descripción optimizada de la lista de reproducción (hashtags incluidos)...")
        playlist_meta = generate_playlist_metadata(artist, lp_title, genre, concept)
        register_and_link_lp_playlist(
            youtube, lp_dir.parent, artist, lp_title, playlist_id,
            base_description=playlist_meta.get("description", ""),
            hashtags=playlist_meta.get("hashtags", []),
        )
        print(
            "-> Descripción actualizada, con enlaces cruzados a los demás "
            "álbumes del grupo (y los demás álbumes ya suben también su "
            "enlace a este)."
        )
    if extra_links:
        link_block += f"\n\n{extra_links}"

    from src.streaming_links import load_streaming_links, build_streaming_block
    streaming_block = build_streaming_block(load_streaming_links(lp_dir))
    if streaming_block:
        link_block += f"\n\n{streaming_block}"

    config_path = lp_dir / "config_subida_youtube.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({
            "thumbnails": {str(k): v for k, v in thumbnails.items()},
            "link_block": link_block,
            "playlist_id": playlist_id,
            "idioma": idioma,
            "track_positions": {str(k): v for k, v in track_positions.items()},
        }, f, ensure_ascii=False, indent=2)

    upload_lp_schedule(
        schedule, save_path, thumbnails=thumbnails, playlist_id=playlist_id,
        youtube=youtube, link_block=link_block, idioma=idioma, track_positions=track_positions,
    )

    if any(not item.get("video_id") for item in schedule):
        bat_path = REPO_ROOT / "continuar_subida_youtube.bat"
        print(
            "\nPara que el resto se suba SOLO cada día (sin que tengas que "
            "relanzar nada a mano), configura una Tarea Programada de Windows "
            "UNA sola vez: abre PowerShell y pega esto (cambia la hora si "
            "quieres otra distinta a las 09:00):\n\n"
            f'    schtasks /create /tn "TelvornSubidaYouTube" /tr "{bat_path}" '
            '/sc daily /st 09:00\n\n'
            "A partir de ahí, Windows lanzará solo, todos los días a esa hora, "
            "el siguiente lote de subidas — no hace falta tener PowerShell ni "
            "este programa abiertos. Puedes revisar el progreso en "
            f"{REPO_ROOT / 'logs' / 'subida_youtube.log'}."
        )


def main():
    print("=== Telvorn Automation — procesar LP completo ===\n")

    lp_dir, grupo, lp_name, folder, dossier_path = _discover_lp()
    folder = _extract_zip_if_needed(folder)
    if not Path(folder).is_dir():
        print(f"No encuentro la carpeta: {folder}")
        sys.exit(1)
    audio_files = _find_audio_files(folder)
    if not audio_files:
        print(f"No encuentro ningún .mp3/.wav en {folder}.")
        sys.exit(1)

    print("-> Leyendo el documento del LP y extrayendo los temas (puede tardar un minuto)...")
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
    artist = st.ask("Artista", dossier.get("artist") or grupo)
    lp_title = st.ask("Nombre del LP", dossier.get("lp_title") or lp_name)
    genre = st.ask("Género/estilo", dossier.get("genre"))
    concept = dossier.get("concept", "")
    memory.update({"artist": artist, "genre": genre})

    do_master = st.ask("¿Masterizar los temas contra alguna canción de referencia? [s/N]", "n").lower()
    reference_path = None
    track_references = {}
    if do_master.startswith("s"):
        found_base, found_overrides = _discover_track_references(lp_dir)
        if found_base or found_overrides:
            print("\n-> Referencias de mastering encontradas en la carpeta del LP:")
            if found_base:
                print(f"   Base (resto de temas): {found_base}")
            for tn in sorted(found_overrides):
                print(f"   Tema {tn}: {found_overrides[tn]}")
            usar = st.ask("¿Usar estas referencias tal cual? [S/n]", "s").lower()
            if usar.startswith("s"):
                reference_path = found_base
                track_references = found_overrides
        if reference_path is None and not track_references:
            reference_path = st.ask_path(
                "Ruta a la canción de referencia (mp3/wav) para todos los temas",
                default=memory.get("reference_track"),
            )
            memory["reference_track"] = reference_path

    watermark_logo_light = st.ask_path(
        "Ruta al logo CLARO para la marca de agua de los Shorts (PNG transparente, opcional, Enter para omitir)",
        required=False, default=memory.get("watermark_logo_light"),
    )
    watermark_logo_dark = st.ask_path(
        "Ruta al logo OSCURO (opcional, Enter para omitir)",
        required=False, default=memory.get("watermark_logo_dark"),
    )
    memory["watermark_logo_light"] = watermark_logo_light
    memory["watermark_logo_dark"] = watermark_logo_dark

    thumb_template = st.ask_path(
        "Ruta a la plantilla de miniatura (portada del LP con el logo — se genera "
        "una miniatura por tema, con el nombre del tema, en cuanto su audio esté "
        "listo; Enter para usar un fotograma del vídeo en su lugar)",
        required=False, default=memory.get("thumb_template"),
    )
    memory["thumb_template"] = thumb_template
    st._save_memory(memory)

    have_openai = bool(os.environ.get("OPENAI_API_KEY"))
    have_stock = bool(
        os.environ.get("PEXELS_API_KEY") or os.environ.get("PIXABAY_API_KEY")
        or os.environ.get("COVERR_API_KEY")
    )
    if not have_openai and not have_stock:
        print("  Aviso: no tienes OPENAI_API_KEY ni PEXELS_API_KEY/PIXABAY_API_KEY/COVERR_API_KEY en tu .env — no podré generar portadas para ningún tema. Añade alguna clave antes de continuar.")
        sys.exit(1)

    lp_calendar = _ask_release_calendar(tracks, lp_dir)

    videos_dir = lp_dir / "VIDEOS"
    shorts_dir_root = lp_dir / "SHORTS"
    audio_final_dir = lp_dir / "AUDIO_FINAL"
    miniaturas_dir = lp_dir / "MINIATURAS"
    for d in (videos_dir, shorts_dir_root, audio_final_dir, miniaturas_dir):
        d.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Empezando: {len(pairs)} temas de \"{lp_title}\" ===\n")

    used_video_urls = set()
    thumbnails = {}
    out_dirs = []
    fallos = []
    for audio_path, track in pairs:
        track_title = _track_display_title(track)
        print(f"\n--- Tema {track['number']}: {track['title']} ---")
        try:
            track_reference = track_references.get(track["number"], reference_path)
            if track_reference:
                print(f"   Referencia de mastering: {track_reference}")
            prepared_audio = _prepare_audio(
                str(audio_path), track_reference,
                title=track["title"], artist=artist, album=lp_title, genre=genre,
                track_number=track["number"], total_tracks=len(pairs),
                final_dir=str(audio_final_dir),
            )

            if thumb_template:
                thumb_out = str(miniaturas_dir / f"{_safe_filename(track['title']).replace(' ', '_')}.jpg")
                thumbnails[track["number"]] = make_track_thumbnail(thumb_template, track["title"], thumb_out)
                print(f"   Miniatura generada: {thumbnails[track['number']]}")

            cover = _resolve_cover_unattended(
                artist, track_title, genre, track["context"], have_openai, have_stock, used_video_urls,
            )
            if cover is None:
                raise RuntimeError("no se ha podido conseguir ninguna portada/vídeo para este tema")

            resolved_cover = resolve_cover(cover)
            resolved_list = resolved_cover if isinstance(resolved_cover, list) else [resolved_cover]
            video_clips = [c for c in resolved_list if Path(c).suffix.lower() in VIDEO_EXTENSIONS]

            lyrics_path = None
            if track.get("lyrics"):
                tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", prefix="lp_lyrics_", delete=False, encoding="utf-8")
                tmp.write(track["lyrics"])
                tmp.close()
                lyrics_path = tmp.name
            try:
                out_dir = process_track(
                    prepared_audio, cover, artist, track_title, genre, track["context"],
                    FALLBACK_N_SHORTS, str(videos_dir), lyrics_path=lyrics_path,
                    shorts_out_dir=str(shorts_dir_root),
                    shorts_clips=video_clips if video_clips else None,
                    shorts_per_clip=SHORTS_PER_CLIP,
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

    print(f"\n=== LP procesado: {len(out_dirs)}/{len(pairs)} temas generados ===")
    print(f"   Audio final (DistroKid): {audio_final_dir}")
    print(f"   Vídeos: {videos_dir}")
    print(f"   Shorts: {shorts_dir_root}")
    if thumbnails:
        print(f"   Miniaturas: {miniaturas_dir}")
    if fallos:
        print("Temas que fallaron:")
        for f in fallos:
            print(f"   - {f}")
    if not out_dirs:
        return

    seguir_youtube = st.ask("\n¿Continuar con la programación/subida a YouTube de todo el LP? [s/N]", "n").lower()
    if not seguir_youtube.startswith("s"):
        print("Listo por ahora. Puedes programar YouTube más tarde relanzando esta fase.")
        return

    _run_youtube_phase(
        tracks, videos_dir, shorts_dir_root, lp_calendar, thumbnails, lp_dir,
        artist, lp_title, genre, concept,
    )


if __name__ == "__main__":
    main()
