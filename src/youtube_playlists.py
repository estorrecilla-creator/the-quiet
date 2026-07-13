"""
youtube_playlists.py
Crea y organiza listas de reproducción de YouTube: agrupar los temas de un
LP en el orden narrativo correcto ayuda mucho al alcance real, porque
YouTube premia el "watch time" en cadena (que la gente vaya de un vídeo al
siguiente sin salir del canal).
"""

from googleapiclient.errors import HttpError


def find_playlist_by_title(youtube, title):
    """Busca entre las listas del propio canal una con ese título exacto."""
    request = youtube.playlists().list(part="snippet", mine=True, maxResults=50)
    while request is not None:
        response = request.execute()
        for item in response.get("items", []):
            if item["snippet"]["title"] == title:
                return item["id"]
        request = youtube.playlists().list_next(request, response)
    return None


def create_or_get_playlist(youtube, title, description="", privacy_status="public"):
    """
    Devuelve el id de una lista de reproducción con ese título: si ya
    existe la reutiliza (no crea duplicados si se ejecuta varias veces),
    si no, la crea.
    """
    existing = find_playlist_by_title(youtube, title)
    if existing:
        return existing

    body = {
        "snippet": {"title": title, "description": description},
        "status": {"privacyStatus": privacy_status},
    }
    response = youtube.playlists().insert(part="snippet,status", body=body).execute()
    return response["id"]


def add_video_to_playlist(youtube, playlist_id, video_id, position=None):
    """
    Añade un vídeo a una lista de reproducción, opcionalmente en una
    posición concreta (0 = primero). Si el vídeo ya está en la lista, no
    hace nada (evita duplicados en reintentos).
    """
    snippet = {
        "playlistId": playlist_id,
        "resourceId": {"kind": "youtube#video", "videoId": video_id},
    }
    if position is not None:
        snippet["position"] = position

    try:
        youtube.playlistItems().insert(part="snippet", body={"snippet": snippet}).execute()
    except HttpError as e:
        details = e.error_details if isinstance(e.error_details, list) else []
        is_duplicate = any(
            isinstance(d, dict) and d.get("reason") == "playlistItemDuplicate"
            for d in details
        )
        if is_duplicate:
            return
        raise


def playlist_url(playlist_id: str) -> str:
    return f"https://www.youtube.com/playlist?list={playlist_id}"
