"""
mastering.py
Masteriza el audio con Matchering (https://github.com/sergree/matchering):
open source, gratis, corre en local. Ajusta ecualización y volumen de tu
tema para parecerse a una canción de referencia con el sonido que buscas.
No modifica el contenido de la canción (no corta ni reordena nada), solo
el procesado de masterización. Devuelve un .wav de la misma duración.
"""

from pathlib import Path

import matchering as mg


def master_audio(target_path: str, reference_path: str, out_path: str) -> str:
    """
    `target_path`: tu mezcla (el audio a masterizar).
    `reference_path`: canción de referencia con el sonido deseado.
    `out_path`: dónde guardar el resultado (.wav, 24-bit). Se crea la
    carpeta si no existe.
    Devuelve `out_path`.
    """
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    mg.process(
        target=target_path,
        reference=reference_path,
        results=[mg.pcm24(out_path)],
    )
    return out_path
