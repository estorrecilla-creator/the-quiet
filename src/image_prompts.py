"""
image_prompts.py
Genera prompts de imagen (para portadas) a partir del artista/título/género/
contexto de un tema, usando la API de Claude. Pensado para encadenarse con
src/image_generator.py: primero se generan los prompts, luego se generan
y descargan las imágenes.
"""

import json

import anthropic

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """Eres un director de arte especializado en portadas de música.
Generas prompts de imagen en inglés, muy visuales y concretos (composición,
iluminación, paleta de color, atmósfera), pensados para un generador de
imágenes de IA. Cada prompt debe ser una escena distinta pero coherente con
el resto (mismo universo visual/atmósfera), para que al encadenarlas en un
vídeo con movimiento de cámara se sientan parte del mismo tema. No incluyas
texto/letras/logos en la imagen. Responde ÚNICAMENTE con JSON válido, sin
texto adicional ni bloques de markdown."""

USER_TEMPLATE = """Genera {n_images} prompts de imagen distintos para las portadas
de este tema musical.

Artista: {artist}
Título del tema: {track_title}
Género/estilo: {genre}
Contexto/concepto: {context}

Devuelve un JSON con esta forma exacta:
{{"prompts": ["prompt en inglés 1", "prompt en inglés 2", "..."]}}
"""


def generate_image_prompts(artist, track_title, genre, context, n_images=3):
    client = anthropic.Anthropic()  # usa ANTHROPIC_API_KEY del entorno

    user_prompt = USER_TEMPLATE.format(
        n_images=n_images, artist=artist, track_title=track_title,
        genre=genre, context=context,
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = "".join(
        block.text for block in response.content if block.type == "text"
    )
    raw_text = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    result = json.loads(raw_text)
    return result["prompts"]


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv
    load_dotenv()

    prompts = generate_image_prompts(
        artist=sys.argv[1], track_title=sys.argv[2], genre=sys.argv[3], context=sys.argv[4],
        n_images=int(sys.argv[5]) if len(sys.argv) > 5 else 3,
    )
    print(json.dumps(prompts, indent=2, ensure_ascii=False))
