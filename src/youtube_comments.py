"""
youtube_comments.py
Publica (y actualiza) un comentario del propio canal en un vídeo ya
subido — mucha gente no despliega la descripción, pero sí lee los
comentarios de arriba, así que es un sitio extra donde dejar el enlace
al tema completo o a las plataformas de streaming.

Aviso importante: YouTube NO tiene ninguna forma pública, vía API, de
FIJAR un comentario arriba de todo (eso solo se puede hacer a mano desde
YouTube Studio o la propia web, hay que hacerlo tú si lo quieres). Esto
publica el comentario del canal, que ya suele aparecer destacado en
"Comentarios principales" por venir del propio creador, pero fijarlo
arriba de verdad requiere ese paso manual.
"""


def post_comment(youtube, video_id: str, text: str) -> str:
    """Publica un comentario del canal autenticado en `video_id`. Devuelve su id."""
    body = {
        "snippet": {
            "videoId": video_id,
            "topLevelComment": {"snippet": {"textOriginal": text}},
        }
    }
    response = youtube.commentThreads().insert(part="snippet", body=body).execute()
    return response["id"]


def update_comment(youtube, comment_thread_id: str, text: str):
    """
    Cambia el texto de un comentario ya publicado por el canal (ej. para
    añadirle los enlaces de streaming en cuanto se conocen, sin publicar
    uno nuevo y duplicado).
    """
    current = youtube.commentThreads().list(part="snippet", id=comment_thread_id).execute()
    items = current.get("items", [])
    if not items:
        return
    top_comment = items[0]["snippet"]["topLevelComment"]
    top_comment["snippet"]["textOriginal"] = text
    youtube.comments().update(part="snippet", body=top_comment).execute()
