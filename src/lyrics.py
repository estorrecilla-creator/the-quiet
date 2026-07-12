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
        start = f"{int(m.group(1))}:{m.group(2)}:{m.group(3)}.{m.group(4)[:2]}"
        end = f"{int(m.group(5))}:{m.group(6)}:{m.group(7)}.{m.group(8)[:2]}"
        text_lines = lines[lines.index(time_line) + 1:]
        text = "\\N".join(text_lines)
        entries.append((start, end, text))
    return entries


def srt_to_ass(srt_path: str, width: int, height: int, margin_v: int, font_size: int = 26) -> str:
    entries = _parse_srt(srt_path)

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
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".ass", prefix="lyrics_", delete=False, encoding="utf-8"
    )
    tmp.write("\n".join(lines))
    tmp.close()
    return tmp.name


def subtitles_filter_fragment(ass_path: str) -> str:
    path = escape_path(ass_path)
    return f"subtitles=filename='{path}'"
