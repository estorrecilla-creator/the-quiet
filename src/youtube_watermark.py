"""
youtube_watermark.py
Sube el logo del canal como "watermark" nativo de YouTube: una vez
configurado, YouTube lo superpone automáticamente en todos los vídeos
largos del canal (no hace falta tocar nada por cada subida). No aplica a
los Shorts (YouTube no muestra el watermark de canal ahí), por eso los
Shorts llevan el logo quemado aparte (ver src/watermark.py).

La API ya no admite elegir la esquina (el campo `position` está
"deprecated"; la única esquina no obsoleta es la superior derecha, que es
donde aparece siempre) — por eso la marca de agua propia (nombre del tema,
ver src/watermark.py) se coloca a propósito en la esquina superior
IZQUIERDA en vídeo principal y Shorts, para no pisarse con ella.
"""


def set_channel_watermark(youtube, image_path: str):
    """
    Sube `image_path` (logo, admite PNG con transparencia) como watermark
    del canal autenticado, visible desde el principio de cada vídeo largo
    durante toda su duración.
    """
    from googleapiclient.http import MediaFileUpload

    channels_resp = youtube.channels().list(part="id", mine=True).execute()
    channel_id = channels_resp["items"][0]["id"]

    youtube.watermarks().set(
        channelId=channel_id,
        media_body=MediaFileUpload(image_path),
        body={"timing": {"type": "offsetFromStart", "offsetMs": "0"}},
    ).execute()

    return channel_id


def unset_channel_watermark(youtube):
    channels_resp = youtube.channels().list(part="id", mine=True).execute()
    channel_id = channels_resp["items"][0]["id"]
    youtube.watermarks().unset(channelId=channel_id).execute()
    return channel_id
