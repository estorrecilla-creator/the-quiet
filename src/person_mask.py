"""
person_mask.py
Detecta la silueta de una persona en la portada (si la hay) usando el
modelo ligero de segmentación de MediaPipe (selfie_segmenter, incluido en
assets/), para poder componer el punto de luz por detrás de la persona y
por delante del resto de la imagen.
"""

import tempfile
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter
from skimage import io

MODEL_PATH = str(Path(__file__).resolve().parent.parent / "assets" / "selfie_segmenter.tflite")


def extract_person_cutout(cover_path: str, min_fraction: float = 0.01):
    """
    Devuelve la ruta a un PNG RGBA con los píxeles de la persona detectada
    (opacos, color original) y el resto transparente, o None si no se
    detecta una silueta clara en la portada.
    """
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.ImageSegmenterOptions(base_options=base_options, output_category_mask=True)

    with vision.ImageSegmenter.create_from_options(options) as segmenter:
        mp_image = mp.Image.create_from_file(cover_path)
        result = segmenter.segment(mp_image)
        mask = result.category_mask.numpy_view()

    person = mask == 255
    if person.mean() < min_fraction:
        return None

    soft_mask = gaussian_filter(person.astype(np.float32), sigma=3)
    soft_mask = (soft_mask.clip(0, 1) * 255).astype(np.uint8)

    rgb = io.imread(cover_path)
    if rgb.ndim == 2:
        rgb = np.stack([rgb] * 3, axis=-1)
    rgb = rgb[..., :3]

    rgba = np.dstack([rgb, soft_mask])

    tmp = tempfile.NamedTemporaryFile(suffix=".png", prefix="person_", delete=False)
    tmp.close()
    io.imsave(tmp.name, rgba, check_contrast=False)
    return tmp.name


def blank_rgba_like(image_path: str) -> str:
    """PNG RGBA totalmente transparente, con el mismo tamaño que `image_path`.
    Se usa para las imágenes de una portada múltiple donde no se detectó
    ninguna persona, para poder concatenarlas junto a las que sí tienen."""
    img = io.imread(image_path)
    h, w = img.shape[:2]
    rgba = np.zeros((h, w, 4), dtype=np.uint8)

    tmp = tempfile.NamedTemporaryFile(suffix=".png", prefix="blank_", delete=False)
    tmp.close()
    io.imsave(tmp.name, rgba, check_contrast=False)
    return tmp.name
