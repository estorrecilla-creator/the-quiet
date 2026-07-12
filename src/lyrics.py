"""
lyrics.py
Superpone letra sincronizada sobre el vídeo a partir de un archivo .srt que
aporta el usuario (con los tiempos exactos de entrada/salida de cada línea).

Genera un .ass temporal con la resolución del vídeo declarada explícitamente
(PlayResX/PlayResY). Es necesario: cuando se le pasa un .srt "pelado" al
filtro `subtitles` de ffmpeg, éste lo convierte a ASS con una resolución de
referencia que no coincide con la del vídeo real, y el tamaño/posición del
texto queda descuadrado sin importar qué valores se le den. Declarándola
explícitamente en un .ass, el tamaño y el margen quedan exactos.

El archivo .srt de entrada es el formato estándar de subtítulos:

    1
    00:00:12,500 --> 00:00:16,000
    primera línea de la letra

    2
    00:00:16,200 --> 00:00:19,800
    segunda línea de la letra

Se puede generar a mano, o con cualquier editor de subtítulos (Aegisub,
Subtitle Edit...) escuchando la canción y marcando el tiempo de cada línea.
"""

import re
import tempfile

from src.ffmpeg_utils import escape_path

_SRT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)


def _parse_srt(srt_path: str):
    """Devuelve [(start_seg, end_seg, text), ...] en segundos (float)."""
    with open(srt_path, encoding="utf-8") as f:
        content = f.read()

    entries = []
    blocks = re.split(r"\n\s*\n", content.strip())
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        time_line = next((l for l in lines if "-->" in l), None)
        if not time_line:
            continue
        m = _SRT_TIME_RE.search(time_line)
        if not m:
            continue
        start = (
            int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            + int(m.group(4)) / 1000
        )
        end = (
            int(m.group(5)) * 3600 + int(m.group(6)) * 60 + int(m.group(7))
            + int(m.group(8)) / 1000
        )
        text_lines = lines[lines.index(time_line) + 1:]
        text = "\\N".join(text_lines)
        entries.append((start, end, text))
    return entries


def _format_ass_time(t: float) -> str:
    t = max(t, 0.0)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def srt_to_ass(
    srt_path: str,
    width: int,
    height: int,
    margin_v: int,
    font_size: int = 58,
    offset: float = 0.0,
    duration: float = None,
) -> str:
    """
    Convierte un .srt a .ass con la resolución del vídeo declarada.
    Si se pasan `offset`/`duration` (uso en Shorts, que son un recorte del
    tema completo), las líneas se desplazan restando `offset` y se recortan
    al rango [0, duration], descartando las que caigan fuera por completo.
    """
    entries = _parse_srt(srt_path)

    if offset or duration is not None:
        shifted = []
        for start, end, text in entries:
            s = start - offset
            e = end - offset
            if duration is not None and (e <= 0 or s >= duration):
                continue
            s = max(s, 0.0)
            if duration is not None:
                e = min(e, duration)
            shifted.append((s, e, text))
        entries = shifted

    header = f"""[Script Info]
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},&H00FFFFFF,&H00000000,&H00000000,0,0,1,2,1,2,10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = [header]
    for start, end, text in entries:
        lines.append(
            f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},"
            f"Default,,0,0,0,,{text}"
        )

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".ass", prefix="lyrics_", delete=False, encoding="utf-8"
    )
    tmp.write("\n".join(lines))
    tmp.close()
    return tmp.name


def subtitles_filter_fragment(ass_path: str) -> str:
    path = escape_path(ass_path)
    return f"subtitles=filename='{path}'"
