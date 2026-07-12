"""
metadata_generator.py
Genera título, descripción y hashtags para YouTube (vídeo largo y Shorts)
usando la API de Claude. Requiere ANTHROPIC_API_KEY en el entorno.

Uso:
    from metadata_generator import generate_metadata
    meta = generate_metadata(
        artist="Telvorn",
        track_title="Caminante",
        genre="doom-folk / post-rock / rock ibérico",
        context="LP conceptual sobre...",
        content_type="main"  # o "short"
    )
"""

import os
import json
import anthropic

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """Eres el responsable de marketing musical del proyecto. Generas
metadatos de YouTube optimizados para descubrimiento (SEO) sin caer en clickbait
ni en promesas falsas. El tono debe ser coherente con la identidad artística
del proyecto. Responde ÚNICAMENTE con JSON válido, sin texto adicional ni
bloques de markdown."""

USER_TEMPLATE = """Genera metadatos de YouTube para esta pieza musical.

Artista: {artist}
Título del tema: {track_title}
Género/estilo: {genre}
Contexto/concepto del álbum o tema: {context}
Tipo de contenido: {content_type_label}

Devuelve un JSON con esta forma exacta:
{{
  "title": "string, máx 100 caracteres, con hook si es short",
  "description": "string, 3-5 líneas, incluye contexto artístico + llamada a la acción",
  "hashtags": ["#etiqueta1", "#etiqueta2", "... 8-12 hashtags relevantes, mezcla de nicho y genéricos"],
  "tags_youtube": ["palabra clave 1", "palabra clave 2", "... 10-15 tags para el campo de YouTube (no hashtags, keywords sueltas)"]
}}
"""


def generate_metadata(artist, track_title, genre, context, content_type="main"):
    client = anthropic.Anthropic()  # usa ANTHROPIC_API_KEY del entorno

    content_type_label = (
        "Vídeo largo de YouTube (tema completo o LP)"
        if content_type == "main"
        else "YouTube Short (15-60s, fragmento del tema)"
    )

    user_prompt = USER_TEMPLATE.format(
        artist=artist,
        track_title=track_title,
        genre=genre,
        context=context,
        content_type_label=content_type_label,
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

    return json.loads(raw_text)


if __name__ == "__main__":
    import sys

    result = generate_metadata(
        artist=sys.argv[1],
        track_title=sys.argv[2],
        genre=sys.argv[3],
        context=sys.argv[4],
        content_type=sys.argv[5] if len(sys.argv) > 5 else "main",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
