"""
face_detection.py
Detección de caras humanas con OpenCV (cascada de Haar), reutilizada en
dos sitios del pipeline: clasificar planos de película como "primer
plano" (film_editor.py) y descartar imágenes/vídeo con gente real de la
NASA (public_domain_archives.py -- "solo espacio, nada de entrevistas ni
gente en la Tierra").

Nota importante: la primera versión de estas dos comprobaciones usaba
`mediapipe.solutions.face_detection`, que ya NO existe en mediapipe
0.10.x (la API nueva, "Tasks", exige descargar aparte un modelo .task) --
en la práctica, con la versión de mediapipe que instala pip hoy, esa
llamada lanzaba AttributeError, que el propio código atrapaba como
"mediapipe no disponible" y se degradaba en SILENCIO a "no hay cara
detectada" siempre, sin avisar de nada (comprobado: nunca detectaba ni un
solo primer plano ni una sola cara humana real). El cascade de Haar de
OpenCV no tiene ese problema y no depende de ninguna descarga en tiempo
de ejecución: el archivo va incluido aquí mismo en el repo
(src/data/haarcascade_frontalface_default.xml, licencia Intel/BSD de
OpenCV, la misma con la que se distribuye siempre).
"""

from pathlib import Path

import cv2

_DATA_DIR = Path(__file__).parent / "data"
# frontal + perfil: un retrato/entrevista rara vez es 100% de frente, y el
# cascade frontal por sí solo se deja bastantes fotos con la cara girada.
_CASCADE_FILES = ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")
_cascades = None


def _get_cascades():
    global _cascades
    if _cascades is None:
        _cascades = [cv2.CascadeClassifier(str(_DATA_DIR / name)) for name in _CASCADE_FILES]
    return _cascades


def frame_has_prominent_face(image, min_face_area_fraction: float = 0.03) -> bool:
    """
    `image`: array RGB (alto x ancho x 3, uint8). Devuelve True si
    detecta una cara (de frente o de perfil) que ocupa al menos
    `min_face_area_fraction` del fotograma (una cara pequeña de fondo no
    cuenta; una cara de primer plano/entrevista/retrato sí). También se
    prueba la imagen reflejada horizontalmente, porque el cascade de
    perfil de OpenCV solo está entrenado para un lado de la cara."""
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        h, w = gray.shape[:2]
        if h == 0 or w == 0:
            return False
        # las fotos de la NASA a veces llegan en resoluciones enormes
        # (8000x8000+); reescalar antes de la cascada es mucho más rápido
        # y evita timeouts, sin cambiar el resultado (la fracción de área
        # de la cara es invariante a la escala).
        max_side = 1280
        if max(h, w) > max_side:
            scale = max_side / max(h, w)
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)))
        rh, rw = gray.shape[:2]
        # minSize son PÍXELES, no una fracción -- si no se recalcula tras
        # reescalar, una cara que sí cumple min_face_area_fraction puede
        # quedar por debajo del mínimo en píxeles y no detectarse nunca.
        min_face_side = max(20, int((min_face_area_fraction * rh * rw) ** 0.5))
        for candidate in (gray, cv2.flip(gray, 1)):
            for cascade in _get_cascades():
                faces = cascade.detectMultiScale(
                    candidate, scaleFactor=1.1, minNeighbors=5,
                    minSize=(min_face_side, min_face_side),
                )
                for (_x, _y, fw, fh) in faces:
                    if (fw * fh) / (rh * rw) >= min_face_area_fraction:
                        return True
        return False
    except Exception:
        return False
