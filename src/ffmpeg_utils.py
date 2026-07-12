"""
ffmpeg_utils.py
Utilidades compartidas para construir comandos/filtros de ffmpeg.
"""


def escape_path(path: str) -> str:
    """Escapa una ruta para usarla como valor de opción dentro de un filtro
    de ffmpeg. Convierte separadores a "/" y escapa los dos puntos (rompen
    el parseo incluso entre comillas simples, por ejemplo con la letra de
    unidad "C:" en Windows) y las comillas simples."""
    path = path.replace("\\", "/")
    path = path.replace(":", r"\:")
    path = path.replace("'", r"\'")
    return path
