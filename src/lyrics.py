"""
lyrics.py
Superpone letra sincronizada sobre el vídeo a partir de un archivo .srt que
aporta el usuario (con los tiempos exactos de entrada/salida de cada línea),
usando el filtro `subtitles` de ffmpeg (requiere libass).

El archivo .srt es el formato estándar de subtítulos:

    1
    00:00:12,500 --> 00:00:16,000
    primera línea de la letra

    2
    00:00:16,200 --> 00:00:19,800
    segunda línea de la letra

Se puede generar a mano, o con cualquier editor de subtítulos (Aegisub,
Subtitle Edit...) escuchando la canción y marcando el tiempo de cada línea.
"""

from src.ffmpeg_utils import escape_path


def subtitles_filter_fragment(srt_path: str, margin_v: int, font_size: int = 42) -> str:
    path = escape_path(srt_path)
    style = (
        f"FontName=Arial,FontSize={font_size},"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=2,Shadow=1,Alignment=2,"
        f"MarginV={margin_v}"
    )
    return f"subtitles=filename='{path}':force_style='{style}'"
