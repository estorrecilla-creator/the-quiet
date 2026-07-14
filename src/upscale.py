"""
upscale.py
Da más nitidez a un clip de vídeo con IA (Real-ESRGAN a través de
Video2X), útil para algún clip de stock que llegue justo de calidad
(justo en el mínimo HD). Es la única mejora de este proyecto que NO corre
por sí sola dentro de este repositorio: Video2X es un programa aparte
(gratis, de código abierto) que hay que instalar tú una vez, y necesita
una GPU con soporte Vulkan medianamente decente — si no la tienes, o el
proceso es demasiado lento, simplemente no lo uses; el resto del pipeline
funciona igual sin él.

Instalación de Video2X (gratis): https://docs.video2x.org/installing/index.html
En Windows, el instalador añade `video2x` al PATH; si no, añade
`%LOCALAPPDATA%\\Programs\\video2x` al PATH a mano.
"""

import shutil
import subprocess


def is_video2x_available() -> bool:
    return shutil.which("video2x") is not None


def upscale_video(input_path: str, output_path: str, scale: int = 2, processor: str = "realesrgan") -> str:
    """
    Escala `input_path` x`scale` veces (2 o 4 son los valores habituales)
    con Video2X/Real-ESRGAN y lo guarda en `output_path`. Necesita el
    programa `video2x` instalado y accesible en el PATH — si no lo
    encuentra, lanza un error explicando cómo instalarlo, en vez de fallar
    con un mensaje críptico de "comando no encontrado".
    """
    if not is_video2x_available():
        raise RuntimeError(
            "No encuentro el programa 'video2x' en el PATH. Instálalo (gratis) "
            "desde https://docs.video2x.org/installing/index.html y vuelve a "
            "intentarlo — necesita además una GPU con soporte Vulkan."
        )

    result = subprocess.run(
        ["video2x", "-i", input_path, "-o", output_path, "-p", processor, "-s", str(scale)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Video2X no pudo escalar el vídeo:\n{result.stderr[-2000:]}")
    return output_path


if __name__ == "__main__":
    import sys

    src, out = sys.argv[1], sys.argv[2]
    scale = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    upscale_video(src, out, scale=scale)
    print(f"Generado: {out}")
