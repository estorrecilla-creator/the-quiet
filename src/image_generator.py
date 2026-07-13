"""
image_generator.py
Genera imágenes de portada a partir de prompts de texto usando la API de
imágenes de OpenAI, y las descarga directamente a la carpeta de un tema en
input/. Requiere OPENAI_API_KEY en el entorno (.env).

Uso:
    from src.image_generator import generate_cover_images
    paths = generate_cover_images(
        prompts=["prompt de la primera portada...", "prompt de la segunda..."],
        out_dir="input/mi_tema",
    )
"""

import base64
import os
from pathlib import Path

import openai

MODEL = "gpt-image-1"
DEFAULT_SIZE = "1536x1024"  # apaisado, encaja bien con el vídeo horizontal 1920x1080


def generate_cover_images(prompts, out_dir, size=DEFAULT_SIZE, model=MODEL, start_index=1):
    """
    Genera una imagen por cada prompt de `prompts` y las guarda en `out_dir`
    como 01.png, 02.png, ... empezando en `start_index` (el orden numérico
    es el orden en el que main.py las usará para el vídeo, cada una con su
    propio movimiento de cámara). `start_index` permite generar/rellenar un
    hueco concreto (ej. el slot 3 de una secuencia) sin pisar los demás.
    Devuelve la lista de rutas guardadas, en orden.
    """
    client = openai.OpenAI()  # usa OPENAI_API_KEY del entorno

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    saved = []
    for offset, prompt in enumerate(prompts):
        i = start_index + offset
        print(f"-> Generando imagen {offset + 1}/{len(prompts)}...")
        result = client.images.generate(model=model, prompt=prompt, size=size, n=1)
        image_bytes = base64.b64decode(result.data[0].b64_json)

        image_path = out_path / f"{i:02d}.png"
        with open(image_path, "wb") as f:
            f.write(image_bytes)
        saved.append(str(image_path))

    return saved


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv
    load_dotenv()

    out_dir = sys.argv[1]
    prompts = sys.argv[2:]
    if not prompts:
        print("Uso: python -m src.image_generator <carpeta_salida> \"prompt 1\" \"prompt 2\" ...")
        sys.exit(1)

    paths = generate_cover_images(prompts, out_dir)
    print("Generadas:", paths)
