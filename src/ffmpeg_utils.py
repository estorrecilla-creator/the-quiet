"""
ffmpeg_utils.py
Utilidades compartidas para construir comandos/filtros de ffmpeg.
"""


def escape_path(path: str) -> str:
    """Escapa una ruta para usarla como valor de opción dentro de un filtro
    de ffmpeg (barras invertidas y dos puntos de unidad dan problemas en
    Windows si no se tratan)."""
    return path.replace("\\", "/").replace("'", r"\'")
