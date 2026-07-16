"""
image_prompts.py
Genera prompts de imagen (para portadas) a partir del artista/título/género/
contexto de un tema, usando la API de Claude. Pensado para encadenarse con
src/image_generator.py: primero se generan los prompts, luego se generan
y descargan las imágenes.
"""

import json

from src.anthropic_utils import call_claude_json

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """Eres un director de arte especializado en portadas de música.
Generas prompts de imagen en inglés, muy visuales y concretos (composición,
iluminación, paleta de color, atmósfera), pensados para un generador de
imágenes de IA. Cada prompt debe ser una escena distinta pero coherente con
el resto (mismo universo visual/atmósfera), para que al encadenarlas en un
vídeo con movimiento de cámara se sientan parte del mismo tema. No incluyas
texto/letras/logos en la imagen.

Estética visual por defecto: aspecto vintage de los años 70-80 — grano de
película analógica, colores algo desaturados o cálidos, textura de
película antigua, iluminación cinematográfica de esa época (nada de look
digital limpio/moderno). Añade términos como "vintage film grain",
"70s film photography", "analog film texture", "faded retro colors" salvo
que el contexto del tema pida explícitamente otra estética distinta.

Responde ÚNICAMENTE con JSON válido, sin texto adicional ni bloques de
markdown."""

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
    user_prompt = USER_TEMPLATE.format(
        n_images=n_images, artist=artist, track_title=track_title,
        genre=genre, context=context,
    )
    result = call_claude_json(SYSTEM_PROMPT, user_prompt, max_tokens=1000, model=MODEL)
    return result["prompts"]


STOCK_SYSTEM_PROMPT = """Eres un editor de vídeo buscando metraje de stock (banco de
vídeo libre de derechos tipo Pexels/Pixabay) para acompañar un tema musical.
Generas búsquedas cortas en inglés (2-4 palabras, como las que escribirías en
el buscador de un banco de vídeo), de escenas concretas y filmables de
verdad (nada abstracto ni imposible de encontrar como metraje real).

Prioridad clave: busca EMOCIONES antes que OBJETOS. Una escena con una
persona/situación que transmita un estado de ánimo concreto (soledad,
anhelo, calma, tensión, melancolía...) siempre gana a un objeto suelto sin
nadie ni nada que lo habite — mejor "person alone rain window" que "rain
window", mejor "quiet solitude empty room" que "empty room", mejor "man
waiting train station" que "train station". Solo recurre a un objeto sin
presencia humana/emocional si de verdad no hay forma de expresar la
emoción de la escena de otra manera.

Regla estricta sobre personas: nunca en primer plano ni mirando a cámara.
Si una escena incluye una persona, tiene que estar de espaldas, de lejos,
en silueta, o fuera de foco/en segundo plano — nunca un rostro reconocible
ni contacto visual con la cámara. Usa términos como "from behind", "distant
figure", "silhouette", "walking away", "back turned", "far away in frame".
Evita por completo términos que impliquen rostro o mirada frontal como
"face", "portrait", "close-up", "looking at camera", "eye contact",
"selfie".

Estética visual por defecto: aspecto vintage de los años 70-80 — busca
metraje con grano de película analógica, look retro/envejecido, colores
algo desaturados o cálidos, textura de cine antiguo (nada de vídeo
digital moderno y limpio). Añade a las búsquedas términos como "vintage
film grain", "retro 70s film", "super 8 footage", "analog film texture",
"faded vintage" cuando encajen con la escena, salvo que el contexto del
tema pida explícitamente otra estética distinta.

Cada búsqueda debe ser distinta pero coherente con el resto (mismo
universo visual/atmósfera). Responde ÚNICAMENTE con JSON válido, sin
texto adicional ni bloques de markdown."""

STOCK_USER_TEMPLATE = """Genera {n_queries} búsquedas cortas de vídeo de stock para
acompañar este tema musical.

Artista: {artist}
Título del tema: {track_title}
Género/estilo: {genre}
Contexto/concepto: {context}

Devuelve un JSON con esta forma exacta:
{{"queries": ["búsqueda corta en inglés 1", "búsqueda corta en inglés 2", "..."]}}
"""


def generate_stock_queries(artist, track_title, genre, context, n_queries=3):
    """
    Como generate_image_prompts(), pero para búsquedas de vídeo de stock:
    términos cortos y concretos (algo que de verdad exista como metraje
    filmado), no prompts elaborados de generación de imagen.
    """
    user_prompt = STOCK_USER_TEMPLATE.format(
        n_queries=n_queries, artist=artist, track_title=track_title,
        genre=genre, context=context,
    )
    result = call_claude_json(STOCK_SYSTEM_PROMPT, user_prompt, max_tokens=500, model=MODEL)
    return result["queries"]


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv
    load_dotenv()

    prompts = generate_image_prompts(
        artist=sys.argv[1], track_title=sys.argv[2], genre=sys.argv[3], context=sys.argv[4],
        n_images=int(sys.argv[5]) if len(sys.argv) > 5 else 3,
    )
    print(json.dumps(prompts, indent=2, ensure_ascii=False))
