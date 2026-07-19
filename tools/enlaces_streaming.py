"""
enlaces_streaming.py — cuando ya tengas los enlaces de Spotify/Apple
Music/etc. de un LP (normalmente días o semanas después de haberlo
subido a YouTube, en cuanto DistroKid termina de distribuirlo), pégalos
aquí UNA vez: se guardan y se enlazan solos en la descripción de todos
los vídeos y Shorts YA subidos de ese LP, y en su lista de reproducción
— no hace falta tocarlos uno a uno a mano. Los vídeos que todavía no se
hayan subido (por la cuota diaria) también los llevarán en cuanto les
toque.

Uso:
    python tools/enlaces_streaming.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

import subir_tema as st
from src.lp_shorts_schedule import load_lp_schedule, save_lp_schedule
from src.streaming_links import PLATFORMS, build_streaming_block, load_streaming_links, save_streaming_links

MUSICA_DIR = REPO_ROOT / "MUSICA"


def _list_subdirs(path):
    if not path.is_dir():
        return []
    return sorted(p.name for p in path.iterdir() if p.is_dir())


def _pick_from_list(prompt, options, what):
    if options:
        print(f"  {what} ya existentes: {', '.join(options)}")
    else:
        print(f"  Todavía no hay ninguna carpeta de {what.lower()}.")
    while True:
        value = st.ask(prompt)
        match = next((o for o in options if o.lower() == value.lower()), None)
        if match:
            return match
        print(f"  No encuentro \"{value}\" entre: {', '.join(options)}.")


def main():
    print("=== Enlaces de streaming (Spotify, Apple Music...) ===\n")

    grupo = _pick_from_list("Grupo", _list_subdirs(MUSICA_DIR), "Grupos")
    group_dir = MUSICA_DIR / grupo
    lp_name = _pick_from_list("LP", _list_subdirs(group_dir), "LPs de este grupo")
    lp_dir = group_dir / lp_name

    existing = load_streaming_links(lp_dir)
    if existing:
        print("\nYa tenías guardados estos enlaces (Enter para dejarlos igual, o pega uno nuevo para cambiarlo):")

    print("\nPega el enlace de cada plataforma (Enter para omitir la que no tengas):")
    links = {}
    for key, label in PLATFORMS:
        default = existing.get(key)
        raw = st.ask(f"  {label}", default=default, required=False)
        if raw:
            links[key] = raw

    if not links:
        print("\nNo has dado ningún enlace, no hay nada que guardar.")
        return

    save_streaming_links(lp_dir, links)
    print(f"\nGuardado en: {lp_dir / 'enlaces_streaming.json'}")

    schedule_path = lp_dir / "calendario_youtube.json"
    if not schedule_path.exists():
        print(
            "Este LP todavía no tiene ningún vídeo subido a YouTube — se "
            "usarán en cuanto empiece la subida."
        )
        return

    schedule = load_lp_schedule(schedule_path)
    uploaded = [item for item in schedule if item.get("video_id")]

    block = build_streaming_block(links)

    from src.youtube_uploader import get_authenticated_service
    youtube = get_authenticated_service()

    config_path = lp_dir / "config_subida_youtube.json"
    if config_path.exists():
        import json

        from src.discografia import update_playlist_streaming_links

        config = json.loads(config_path.read_text(encoding="utf-8"))
        playlist_id = config.get("playlist_id")
        if playlist_id:
            updated = update_playlist_streaming_links(
                youtube, group_dir, grupo, playlist_id, links,
            )
            if updated:
                print("-> Lista de reproducción actualizada con los enlaces de streaming.")

    if not uploaded:
        print(
            "Este LP todavía no tiene ningún vídeo subido — los enlaces se "
            "usarán en cuanto empiece la subida."
        )
        return

    print(f"\n-> Añadiendo los enlaces a los {len(uploaded)} vídeos ya subidos...")
    from src.youtube_uploader import append_to_video_description
    from src.streaming_links import BLOCK_MARKER
    from src.youtube_comments import post_comment, update_comment
    from src.lp_shorts_schedule import _is_published

    pending_comment = 0
    for item in uploaded:
        # la descripción se puede editar aunque el vídeo siga programado/
        # privado, así que esto funciona siempre.
        append_to_video_description(item["video_id"], block, marker=BLOCK_MARKER)
        # el comentario NO -- YouTube lo rechaza en vídeos todavía
        # privados (403 "forbidden"). Si aún no es público, se deja para
        # que lo coja solo la subida diaria en cuanto le toque publicarse
        # (no es un fallo, es esperado con vídeos programados).
        if not _is_published(item["publish_at_utc"]):
            pending_comment += 1
            continue
        try:
            if item.get("comment_id"):
                update_comment(youtube, item["comment_id"], block)
            else:
                comment_id = post_comment(youtube, item["video_id"], block)
                item["comment_id"] = comment_id
        except Exception as e:
            print(f"   Aviso: no se pudo actualizar el comentario de {item['video_id']} ({e}).")
    save_lp_schedule(schedule, schedule_path)
    if pending_comment:
        print(
            f"({pending_comment} vídeo(s) todavía programado(s)/privado(s) — su "
            "comentario con los enlaces se publicará solo en cuanto se hagan "
            "públicos, sin que tengas que hacer nada.)"
        )
    print(
        "Listo. Los vídeos que todavía falten por subir (por la cuota "
        "diaria) también los llevarán en cuanto les toque."
    )


if __name__ == "__main__":
    main()
