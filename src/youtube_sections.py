"""
youtube_sections.py
Organiza la página de inicio del canal en secciones — lo más parecido que
tiene YouTube a "carpetas": un bloque horizontal por categoría, con su
propio título ("Álbumes" con la lista de reproducción de cada LP,
"Últimos vídeos" rellenada sola por YouTube...). Se gestiona con el
recurso `channelSections` de la API, distinto de las listas de
reproducción normales.
"""


def _find_section_by_title(youtube, title):
    resp = youtube.channelSections().list(part="snippet,contentDetails", mine=True).execute()
    for item in resp.get("items", []):
        if item.get("snippet", {}).get("title") == title:
            return item
    return None


def add_playlist_to_section(
    youtube, playlist_id: str, section_title: str = "Álbumes",
    style: str = "horizontalRow", position: int = None,
):
    """
    Añade `playlist_id` a la sección con título `section_title` de la
    página de inicio del canal (la crea si no existe todavía). Si el
    playlist ya estaba en la sección, no hace nada — así se puede llamar
    cada vez que se termina de procesar un LP nuevo, sin duplicar ni
    pisar lo que ya había de otros LPs. Devuelve el id de la sección.
    """
    existing = _find_section_by_title(youtube, section_title)
    if existing:
        playlists = list(existing.get("contentDetails", {}).get("playlists", []))
        if playlist_id in playlists:
            return existing["id"]
        playlists.append(playlist_id)
        body = {
            "id": existing["id"],
            "snippet": existing["snippet"],
            "contentDetails": {"playlists": playlists},
        }
        youtube.channelSections().update(part="snippet,contentDetails", body=body).execute()
        return existing["id"]

    snippet = {"type": "multiplePlaylists", "style": style, "title": section_title}
    if position is not None:
        snippet["position"] = position
    body = {"snippet": snippet, "contentDetails": {"playlists": [playlist_id]}}
    resp = youtube.channelSections().insert(part="snippet,contentDetails", body=body).execute()
    return resp["id"]


def ensure_builtin_section(youtube, section_type: str, style: str = "horizontalRow", position: int = None):
    """
    Crea una sección "automática" (sin lista de reproducción propia: la
    rellena YouTube solo) si todavía no existe una de ese tipo en el
    canal — las más habituales son "recentUploads" (últimos vídeos) y
    "popularUploads" (más populares). No hace nada si ya hay una de ese
    mismo tipo (evita duplicados si se relanza el ajuste del canal).
    """
    resp = youtube.channelSections().list(part="snippet", mine=True).execute()
    if any(item.get("snippet", {}).get("type") == section_type for item in resp.get("items", [])):
        return None
    snippet = {"type": section_type, "style": style}
    if position is not None:
        snippet["position"] = position
    resp = youtube.channelSections().insert(part="snippet", body={"snippet": snippet}).execute()
    return resp["id"]
