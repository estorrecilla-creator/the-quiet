"""
youtube_channel.py
Actualiza los ajustes de marca del propio canal (palabras clave y
descripción del "Acerca de") para ayudar a YouTube a entender de qué va
el canal y recomendarlo al público/nicho correcto.
"""


def update_channel_branding(youtube, keywords: str = None, description: str = None):
    """
    `keywords`: cadena con las palabras clave del canal separadas por
    espacios (las que van entre comillas cuentan como una sola), ej.
    '"progressive rock" "atmospheric rock" "concept album"'.
    `description`: texto del "Acerca de" del canal.
    Solo actualiza los campos que se pasen (deja el resto tal cual estaba).
    """
    channels_resp = youtube.channels().list(part="id", mine=True).execute()
    channel_id = channels_resp["items"][0]["id"]

    branding_resp = youtube.channels().list(part="brandingSettings", id=channel_id).execute()
    branding = branding_resp["items"][0]["brandingSettings"]
    channel_branding = branding.setdefault("channel", {})

    if keywords is not None:
        channel_branding["keywords"] = keywords
    if description is not None:
        channel_branding["description"] = description

    youtube.channels().update(
        part="brandingSettings",
        body={"id": channel_id, "brandingSettings": branding},
    ).execute()
