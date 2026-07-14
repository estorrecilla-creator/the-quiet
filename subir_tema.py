"""
subir_tema.py — asistente interactivo.

Detecta solo los audios que hay en input/, recuerda artista/género/contexto
de la vez anterior (config/asistente_memoria.json) y genera el vídeo
principal, los Shorts y los metadatos, sin que tengas que recordar los
parámetros de main.py ni volver a escribir siempre lo mismo.

Uso:
    python subir_tema.py
"""

import json
import os
import sys
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

from main import process_track
from src.image_prompts import generate_image_prompts
from src.image_generator import generate_cover_images

MEMORY_PATH = Path("config") / "asistente_memoria.json"
AUDIO_EXTENSIONS = (".mp3", ".wav")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".m4v")


def _load_memory():
    if MEMORY_PATH.exists():
        try:
            return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_memory(memory):
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")


def _strip_quotes(value):
    # Al arrastrar un archivo a la terminal (sobre todo en Windows), la ruta
    # llega envuelta en comillas: "C:\ruta\archivo.mp3".
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def ask(prompt, default=None, required=True):
    suffix = f" [{default}]" if default else ""
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        value = _strip_quotes(raw) if raw else default
        if value or not required:
            return value
        print("  Este dato es obligatorio.")


def ask_path(prompt, required=True, default=None):
    while True:
        value = ask(prompt, default=default, required=required)
        if not value:
            return None
        if Path(value).expanduser().exists():
            return str(Path(value).expanduser())
        print(f"  No encuentro el archivo: {value}")


def _find_audio_files():
    input_dir = Path("input")
    if not input_dir.is_dir():
        return []
    return sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    )


def _pick_audio():
    files = _find_audio_files()
    if not files:
        print("  No encuentro ningún .mp3/.wav dentro de input/.")
        return ask_path("Ruta al audio (mp3/wav)")

    if len(files) == 1:
        print(f"-> Audio detectado en input/: {files[0]}")
        return str(files[0])

    print("Varios audios encontrados en input/:")
    for i, f in enumerate(files, start=1):
        print(f"   {i}. {f}")
    while True:
        raw = _strip_quotes(input(f"Elige uno [1-{len(files)}] (o pega otra ruta): ").strip())
        if raw.isdigit() and 1 <= int(raw) <= len(files):
            return str(files[int(raw) - 1])
        if raw and Path(raw).expanduser().exists():
            return str(Path(raw).expanduser())
        print("  Opción no válida.")


def _maybe_master_audio(audio_path, memory):
    do_master = ask(
        "¿Masterizar el audio antes de continuar? (con Matchering, gratis y "
        "local; necesita una canción de referencia con el sonido que "
        "buscas) [s/N]", "n"
    ).lower()
    if not do_master.startswith("s"):
        return audio_path

    reference = ask_path(
        "Ruta a la canción de referencia (mp3/wav)",
        default=memory.get("reference_track"),
    )
    memory["reference_track"] = reference
    _save_memory(memory)

    from src.mastering import master_audio
    mastered_dir = Path("mastered")
    mastered_dir.mkdir(exist_ok=True)
    out_path = str(mastered_dir / f"{Path(audio_path).stem}_mastered.wav")
    print("-> Masterizando con Matchering (puede tardar un minuto)...")
    master_audio(audio_path, reference, out_path)
    print(f"   Audio masterizado guardado en: {out_path}")
    return out_path


def _trim_silence_step(audio_path):
    """
    Siempre se aplica: recorta el silencio del principio y del final (no
    el de en medio, ese es parte de la canción) para que el vídeo no
    arranque/acabe con un tramo muerto.
    """
    from src.audio_hygiene import trim_silence
    prepared_dir = Path("prepared")
    prepared_dir.mkdir(exist_ok=True)
    out_path = str(prepared_dir / f"{Path(audio_path).stem}_trimmed.wav")
    trim_silence(audio_path, out_path)
    return out_path


def _check_mono_compatibility_step(audio_path):
    """
    Solo diagnóstico, no toca el audio: avisa si la mezcla pierde mucha
    energía al sumarse a mono (estéreo muy ancho o fase invertida en
    algún punto), algo que se nota en dispositivos/altavoces que
    reproducen en mono.
    """
    from src.audio_hygiene import check_mono_compatibility
    result = check_mono_compatibility(audio_path)
    if result.get("warning"):
        print(
            f"  Aviso: la mezcla pierde {abs(result['diff_db']):.1f} dB de energía al "
            "sumarse a mono (posible cancelación de fase por un estéreo muy "
            "ancho) — puede sonar más floja o rara en dispositivos que "
            "reproducen en mono. No se toca nada automáticamente, es solo un "
            "aviso para que lo revises en tu mezcla si quieres."
        )


def _maybe_denoise_step(audio_path):
    """
    Siempre se comprueba, pero solo se aplica una reducción de ruido muy
    conservadora si de verdad se detecta un suelo de ruido de fondo
    audible — para no arriesgarse a tocar una mezcla que ya está limpia.
    """
    from src.audio_hygiene import denoise_if_needed
    prepared_dir = Path("prepared")
    prepared_dir.mkdir(exist_ok=True)
    out_path = str(prepared_dir / f"{Path(audio_path).stem}_denoised.wav")
    result_path, applied, floor_db = denoise_if_needed(audio_path, out_path)
    if applied:
        print(f"-> Ruido de fondo detectado (suelo ~{floor_db:.0f}dB) — aplicando una reducción suave...")
    return result_path


def _normalize_loudness_step(audio_path):
    """
    Siempre se aplica (no hace falta elegir nada): lleva el volumen final
    al estándar de YouTube/streaming (-14 LUFS) para que ningún tema del
    canal suene más flojo o más fuerte que el resto. Se hace después de
    la masterización opcional, que ajusta tono/color pero no garantiza un
    LUFS exacto.
    """
    from src.loudness import normalize_loudness, TARGET_I
    normalized_dir = Path("normalized")
    normalized_dir.mkdir(exist_ok=True)
    out_path = str(normalized_dir / f"{Path(audio_path).stem}_normalized.wav")
    print(f"-> Normalizando el volumen a {TARGET_I} LUFS (estándar de YouTube/streaming)...")
    normalize_loudness(audio_path, out_path)
    print(f"   Audio con volumen normalizado guardado en: {out_path}")
    print("   (Este es el archivo final: el que se usa para generar los vídeos "
          "y el que puedes subir a DistroKid.)")
    return out_path


def _suggest_clip_count(audio_path, target_seconds=25, max_clips=15, min_clips=3):
    """
    Cuantos clips hacen falta para cubrir la duración del tema sin que
    ninguno tenga que repetirse en bucle muchas veces — cuanto más largo
    el tema, más clips (hasta `max_clips`), en vez de forzar siempre el
    mismo número por defecto.
    """
    try:
        import soundfile as sf
        info = sf.info(audio_path)
        duration = info.frames / info.samplerate
    except Exception:
        return min_clips
    return max(min_clips, min(max_clips, round(duration / target_seconds)))


def _resolve_stock_video_covers(
    artist, title, genre, context, n_images, have_openai, orientation="landscape",
    min_duration=4.0, homogenize=False,
):
    from src.stock_video import find_stock_clip
    from src.image_prompts import generate_stock_queries

    print("-> Generando búsquedas de vídeo de stock a partir del género/contexto "
          "(priorizando emociones sobre objetos)...")
    queries = generate_stock_queries(artist, title, genre, context, n_queries=n_images)
    for i, q in enumerate(queries, start=1):
        print(f"   {i}. {q}")

    suffix = "" if orientation == "landscape" else "_shorts"
    cover_dir = Path("input") / f"{title.replace(' ', '_')}{suffix}"
    cover_dir.mkdir(parents=True, exist_ok=True)

    covers = []
    for i, query in enumerate(queries, start=1):
        print(f"-> Buscando vídeo libre de derechos ({orientation}) para: {query!r}...")
        clip_path = str(cover_dir / f"{i:02d}.mp4")
        result = find_stock_clip(query, clip_path, orientation=orientation, min_duration=min_duration)
        if result:
            print(f"   Encontrado: {clip_path}")
            covers.append(clip_path)
        elif have_openai:
            print("   No encontrado, genero una imagen con IA en su lugar...")
            fallback_prompt = generate_image_prompts(artist, title, genre, context, n_images=1)[0]
            paths = generate_cover_images([fallback_prompt], str(cover_dir), start_index=i)
            covers.append(paths[0])
        else:
            print("   No encontrado (y no hay OPENAI_API_KEY para generar una "
                  "imagen de respaldo) — este hueco se queda sin portada.")

    if not covers:
        print("  No se consiguió ninguna portada por este camino.")
        return None

    if homogenize:
        video_covers = [c for c in covers if Path(c).suffix.lower() in VIDEO_EXTENSIONS]
        if len(video_covers) >= 2:
            print(f"-> Homogeneizando brillo/color entre los {len(video_covers)} clips "
                  "para que el cambio de uno a otro se note menos...")
            from src.color_match import homogenize_clips
            homogenize_clips(video_covers)

    print(f"   Portadas guardadas en: {cover_dir}")
    return str(cover_dir)


def _match_cover_mode(raw, have_stock, have_openai):
    """
    Interpreta la respuesta a "¿tengo las imágenes / vídeo libre de
    derechos / generar con IA?" de forma flexible — no todo el mundo
    responde con la letra exacta entre corchetes, a veces se escribe la
    frase entera ("busca vídeo libre de derechos"). Devuelve "t"/"v"/"g",
    o None si no se reconoce nada (para que el que llama vuelva a
    preguntar en vez de asumir un modo no querido).
    """
    text = raw.strip().lower()

    if text.startswith("t") or "tengo" in text or "imagen" in text:
        return "t"
    if have_stock and (
        text.startswith("v") or "video" in text or "vídeo" in text
        or "stock" in text or "libre" in text
    ):
        return "v"
    if have_openai and (
        text.startswith("g") or "genera" in text or "ia" in text.split()
        or text.endswith(" ia") or text == "ia"
    ):
        return "g"
    return None


def _resolve_cover_interactive(artist, title, genre, context, audio_path):
    have_openai = bool(os.environ.get("OPENAI_API_KEY"))
    have_stock = bool(
        os.environ.get("PEXELS_API_KEY") or os.environ.get("PIXABAY_API_KEY")
        or os.environ.get("COVERR_API_KEY")
    )

    if not have_openai and not have_stock:
        print(
            "  (Nota: no tienes OPENAI_API_KEY ni PEXELS_API_KEY/PIXABAY_API_KEY/"
            "COVERR_API_KEY en tu .env, así que no puedo generar/buscar "
            "portadas automáticamente. Añade alguna para activarlo la "
            "próxima vez.)"
        )
        cover = ask_path(
            "Ruta a la portada (jpg/png), o a una carpeta con varias imágenes "
            "(cada una tendrá su propio movimiento de cámara)"
        )
        return cover, None

    opciones = ["[t]engo las imágenes"]
    if have_stock:
        opciones.append("[v]ídeo libre de derechos")
    if have_openai:
        opciones.append("[g]enerar con IA")
    default_modo = "v" if have_stock else "g"

    while True:
        raw = ask(
            "¿Ya tienes las imágenes de portada, quieres que busque vídeo libre "
            f"de derechos, o que las genere con IA? {' / '.join(opciones)}",
            default_modo,
        )
        modo = _match_cover_mode(raw, have_stock, have_openai)
        if modo:
            break
        print(f"  No he entendido \"{raw}\" — responde con una de estas letras: {' / '.join(opciones)}.")

    if modo == "t":
        cover = ask_path(
            "Ruta a la portada (jpg/png), o a una carpeta con varias imágenes "
            "(cada una tendrá su propio movimiento de cámara)"
        )
        return cover, None

    if modo == "v":
        suggested_n = _suggest_clip_count(audio_path)
        n_images = int(ask(
            "¿Cuántos clips de vídeo buscamos para el vídeo principal? Cuantos "
            "más, menos se nota el bucle en temas largos — para la duración de "
            f"este tema sugiero unos {suggested_n} (podemos usar 10-15 sin "
            "problema si hace falta)", str(suggested_n)
        ))
        cover = _resolve_stock_video_covers(
            artist, title, genre, context, n_images, have_openai, orientation="landscape",
            min_duration=8.0, homogenize=True,
        )
        if cover is None:
            cover = ask_path(
                "Ruta a la portada (jpg/png), o a una carpeta con varias imágenes "
                "(cada una tendrá su propio movimiento de cámara)"
            )
            return cover, None

        print("-> Buscando también una portada vertical propia para los Shorts...")
        shorts_cover = _resolve_stock_video_covers(
            artist, title, genre, context, 1, have_openai, orientation="portrait"
        )
        return cover, shorts_cover

    n_images = int(ask(
        "¿Cuántas imágenes generamos? (cada una tendrá su propio movimiento "
        "de cámara)", "3"
    ))
    print("-> Generando prompts de imagen a partir del género/contexto...")
    prompts = generate_image_prompts(artist, title, genre, context, n_images=n_images)
    for i, p in enumerate(prompts, start=1):
        print(f"   {i}. {p}")

    cover_dir = Path("input") / title.replace(" ", "_")
    print(f"-> Generando {n_images} imágenes con IA (puede tardar un minuto)...")
    generate_cover_images(prompts, str(cover_dir))
    print(f"   Imágenes guardadas en: {cover_dir}")
    return str(cover_dir), None


def main():
    print("=== Telvorn Automation — asistente ===\n")

    audio = _pick_audio()
    suggested_title = Path(audio).stem
    memory = _load_memory()

    audio = _maybe_master_audio(audio, memory)
    audio = _trim_silence_step(audio)
    _check_mono_compatibility_step(audio)
    audio = _maybe_denoise_step(audio)
    audio = _normalize_loudness_step(audio)

    artist = ask("Artista", memory.get("artist"))
    title = ask("Título del tema", suggested_title)
    genre = ask("Género/estilo", memory.get("genre"))
    context = ask("Contexto/concepto del tema", memory.get("context"))

    print("-> Limpiando metadatos del audio (fuera cualquier rastro de la "
          "herramienta usada para componerlo)...")
    from src.metadata_cleaner import clean_audio_metadata
    year = date.today().year
    publisher = os.environ.get("RELEASE_PUBLISHER", artist)
    copyright_holder = os.environ.get("RELEASE_COPYRIGHT_HOLDER", artist)
    clean_audio_metadata(
        audio, title=title, artist=artist, album_artist=artist, genre=genre, year=year,
        composer=artist, lyricist=artist, producer=publisher, publisher=publisher,
        copyright_text=f"© {year} {copyright_holder}",
        phonographic_copyright=f"℗ {year} {copyright_holder}",
    )

    print(
        "  (Marca de agua de los Shorts: al no tener fondo, el logo "
        "necesita una variante clara y otra oscura, para elegir la que "
        "contraste según el vídeo de cada Short. Puedes dar solo una si "
        "no tienes las dos.)"
    )
    watermark_logo_light = ask_path(
        "Ruta al logo CLARO (PNG transparente, para fondos oscuros; "
        "opcional, Enter para omitir)",
        required=False,
        default=memory.get("watermark_logo_light"),
    )
    watermark_logo_dark = ask_path(
        "Ruta al logo OSCURO (PNG transparente, para fondos claros; "
        "opcional, Enter para omitir)",
        required=False,
        default=memory.get("watermark_logo_dark"),
    )

    memory.update({
        "artist": artist, "genre": genre, "context": context,
        "watermark_logo_light": watermark_logo_light,
        "watermark_logo_dark": watermark_logo_dark,
    })
    _save_memory(memory)

    cover, shorts_cover_override = _resolve_cover_interactive(artist, title, genre, context, audio)
    shorts = int(ask("Número de Shorts a generar", "3"))
    lyrics = ask_path(
        "Ruta a la letra (.srt ya sincronizado, o .txt en texto plano para "
        "sincronizar automáticamente; opcional, Enter para omitir)",
        required=False,
    )
    lyrics_offset = 0.0
    if lyrics:
        offset_raw = ask(
            "Ajuste manual de la letra en segundos (positivo = retrasa, "
            "negativo = adelanta; Enter para no ajustar)",
            default="0",
            required=False,
        )
        try:
            lyrics_offset = float(offset_raw) if offset_raw else 0.0
        except ValueError:
            print("  Valor no válido, no se aplicará ajuste.")
            lyrics_offset = 0.0

    out_dir = process_track(
        audio, cover, artist, title, genre, context, shorts, "output",
        lyrics_path=lyrics, lyrics_offset=lyrics_offset,
        shorts_cover_override=shorts_cover_override,
        watermark_logo_light_path=watermark_logo_light,
        watermark_logo_dark_path=watermark_logo_dark,
    )
    print(f"\nListo. Revisa la carpeta: {out_dir}")


if __name__ == "__main__":
    main()
