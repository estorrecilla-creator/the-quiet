"""
star_path.py
Extrae un contorno real de la portada (los límites de las formas/objetos de
la imagen) para que un pequeño punto de luz pueda recorrerlo, en vez de
seguir un movimiento genérico. Usa detección de bordes (Sobel) + trazado de
contornos de scikit-image.
"""

import numpy as np
from skimage import io, color, filters, measure


def _fallback_ellipse_path(n_points: int):
    """Portadas lisas (sin bordes detectables) no tienen contorno que trazar;
    en ese caso el punto de luz sigue una elipse suave inscrita en el
    fotograma en vez de fallar."""
    t = np.linspace(0, 2 * np.pi, n_points, endpoint=False)
    x = 0.5 + 0.35 * np.cos(t)
    y = 0.5 + 0.35 * np.sin(t)
    return list(zip(x, y))


def _resample_contour(contour, n_points):
    diffs = np.diff(contour, axis=0)
    seglen = np.sqrt((diffs ** 2).sum(axis=1))
    cumlen = np.concatenate([[0.0], np.cumsum(seglen)])
    total = cumlen[-1]
    if total <= 0:
        return np.repeat(contour[:1], n_points, axis=0)
    targets = np.linspace(0, total, n_points, endpoint=False)
    rows = np.interp(targets, cumlen, contour[:, 0])
    cols = np.interp(targets, cumlen, contour[:, 1])
    return np.stack([rows, cols], axis=1)


def extract_contour_path(image_path: str, n_points: int = 240, edge_percentile: float = 92.0):
    """
    Devuelve una lista de (x, y) normalizados (0..1) trazando el contorno más
    largo detectado en la imagen, con `n_points` muestreados a distancia
    uniforme a lo largo de su recorrido.
    """
    img = io.imread(image_path)
    if img.ndim == 3:
        gray = color.rgb2gray(img[..., :3])
    else:
        gray = img.astype(float) / 255.0

    edges = filters.sobel(gray)
    level = np.percentile(edges, edge_percentile)
    contours = measure.find_contours(edges, level)
    if not contours:
        return _fallback_ellipse_path(n_points)

    contour = max(contours, key=len)
    resampled = _resample_contour(contour, n_points)

    h, w = gray.shape
    return [(c / w, r / h) for r, c in resampled]
