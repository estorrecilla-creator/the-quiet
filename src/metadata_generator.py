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

import json

from src.anthropic_utils import call_claude_json

MODEL = "claude-sonnet-5"

# Caché opcional de metadatos pre-generados (por ejemplo, cuando se ha
# agotado el saldo de la API a mitad de un LP y se quiere seguir sin
# gastar más créditos en esta parte). Si está cargada, generate_metadata()
# usa lo que haya para ese tema/tipo en vez de llamar a la API; si el tema
# no está en la caché, sigue funcionando con la llamada en directo de
# siempre. Para "short", la caché guarda un POOL de varias variantes por
# tema (no una por cada Short — todos los Shorts de un mismo tema reciben
# igualmente los mismos datos de entrada, así que no aporta nada generar
# una única exacta por cada uno) y se van reutilizando cíclicamente.
_CACHE = None
_SHORT_POOL_INDEX = {}

# Pool generado EN DIRECTO (sin caché de archivo) para Shorts -- se pide
# de una sola vez por tema (barato) en vez de una llamada por Short
# (caro), igual que la caché de archivo, pero sin necesitar preparar
# nada a mano. Ver generate_short_metadata_pool(): fuerza que título,
# descripción Y HASHTAGS varíen de verdad entre Shorts del mismo tema --
# publicar el mismo puñado de hashtags en decenas de vídeos seguidos hace
# que YouTube lo trate como contenido repetitivo y reduce el alcance.
_LIVE_POOL = {}
_LIVE_POOL_INDEX = {}
DEFAULT_SHORT_POOL_SIZE = 12


def load_metadata_cache(path: str) -> None:
    global _CACHE, _SHORT_POOL_INDEX
    with open(path, encoding="utf-8") as f:
        _CACHE = json.load(f)
    _SHORT_POOL_INDEX = {}


def _cached_metadata(track_title: str, content_type: str):
    if _CACHE is None:
        return None
    if content_type == "main":
        return _CACHE.get("main", {}).get(track_title)
    pool = _CACHE.get("shorts_pool", {}).get(track_title)
    if not pool:
        return None
    idx = _SHORT_POOL_INDEX.get(track_title, 0)
    _SHORT_POOL_INDEX[track_title] = idx + 1
    return pool[idx % len(pool)]

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
  "title": "string, máx 100 caracteres. {title_hint}",
  "description": "string. {description_hint}",
  "hashtags": ["#etiqueta1", "#etiqueta2", "#etiqueta3", "3-5 hashtags MÁXIMO y muy relevantes — pasarse de 5 hace que YouTube lo clasifique como spam"],
  "tags_youtube": ["palabra clave 1", "palabra clave 2", "... 10-15 tags para el campo de YouTube (no hashtags, keywords sueltas)"]
}}
"""

# El vídeo largo se beneficia de una descripción extensa (SEO: cuanto más
# contexto real, mejor entiende YouTube de qué trata) con la palabra clave
# principal (título/artista) en la primera frase. Los Shorts usan su propio
# prompt (SHORT_POOL_USER_TEMPLATE, más abajo) que además fuerza variedad
# real entre Shorts del mismo tema -- no comparten estos hints.
_HINTS = {
    "main": {
        "title": "La palabra clave principal (título del tema o artista) cerca del principio.",
        "description": (
            "300-500 palabras. La palabra clave principal (título del tema/artista) en la "
            "PRIMERA frase. Desarrolla el concepto/contexto artístico en profundidad — ayuda a "
            "que YouTube entienda de qué trata, no repitas la misma frase varias veces — y "
            "termina con una llamada a la acción clara."
        ),
    },
}


SHORT_POOL_USER_TEMPLATE = """Genera {n} variantes DISTINTAS de metadatos de YouTube
para Shorts del mismo tema musical (todas parten del mismo tema/género/contexto,
pero se van a publicar como Shorts distintos a lo largo de varias semanas -- no
pueden sonar como la misma publicación reescrita).

Artista: {artist}
Título del tema: {track_title}
Género/estilo: {genre}
Contexto/concepto del álbum o tema: {context}

Reglas de variación (importante, esto es justo lo que se pide):
- Título y descripción: cada variante debe tener un ángulo o gancho distinto
  (una línea de la letra, una imagen del tema, una pregunta, un dato...), no
  sinónimos de la misma frase.
- Título: además del gancho y la frase de búsqueda, termina SIEMPRE con
  1-2 hashtags pegados al final (ej. "...#shorts #progrock") -- ayuda al
  descubrimiento en el feed de Shorts. Mantén "#shorts" fijo si encaja, pero
  varía el segundo hashtag del título entre variantes (no el mismo siempre).
- Hashtags: cada variante lleva 3-5 hashtags (para el campo de hashtags, no
  el título), pero NO uses siempre el mismo conjunto en todas las variantes
  -- mantén como máximo 1-2 hashtags fijos de marca (nombre del artista y/o
  álbum) y varía el resto entre distintas etiquetas reales de género/
  temática/estado de ánimo relevantes para esta pieza (ej: subgéneros,
  adjetivos de atmósfera, "#shorts" cuando aplique, etc.) -- publicar el
  mismo puñado de hashtags en decenas de vídeos seguidos hace que YouTube lo
  trate como contenido repetitivo y reduce el alcance.
- tags_youtube: igual, varía las palabras clave sueltas entre variantes en vez
  de repetir la misma lista.

Devuelve un JSON con esta forma exacta:
{{
  "variants": [
    {{
      "title": "string, máx 100 caracteres, gancho + frase de búsqueda real + 1-2 hashtags al final",
      "description": "string, 3-5 líneas, palabra clave principal en la primera frase",
      "hashtags": ["#etiqueta1", "#etiqueta2", "3-5 hashtags MÁXIMO, variados entre variantes"],
      "tags_youtube": ["palabra clave 1", "... 10-15 tags sueltas, variadas entre variantes"]
    }}
  ]
}}
La lista "variants" debe tener exactamente {n} elementos.
"""


def generate_short_metadata_pool(artist, track_title, genre, context, n=DEFAULT_SHORT_POOL_SIZE):
    """
    Pide de una sola vez (barato) un conjunto de `n` variantes de
    título/descripción/hashtags/tags para los Shorts de un mismo tema,
    forzando que varíen de verdad entre sí -- en particular los hashtags,
    que si no se piden explícitamente tienden a converger siempre en el
    mismo puñado "obviamente correcto" (nombre de artista/álbum/género),
    aunque se llame a la API por separado para cada Short.
    """
    user_prompt = SHORT_POOL_USER_TEMPLATE.format(
        n=n, artist=artist, track_title=track_title, genre=genre, context=context,
    )
    result = call_claude_json(
        SYSTEM_PROMPT, user_prompt, max_tokens=400 * n, model=MODEL,
    )
    return result["variants"]


def _live_pool_metadata(artist, track_title, genre, context):
    pool = _LIVE_POOL.get(track_title)
    if pool is None:
        pool = generate_short_metadata_pool(artist, track_title, genre, context)
        _LIVE_POOL[track_title] = pool
    idx = _LIVE_POOL_INDEX.get(track_title, 0)
    _LIVE_POOL_INDEX[track_title] = idx + 1
    return pool[idx % len(pool)]


def generate_metadata(artist, track_title, genre, context, content_type="main"):
    cached = _cached_metadata(track_title, content_type)
    if cached is not None:
        return cached

    if content_type == "short":
        # un Short suelto reutiliza el mismo tema/género/contexto que
        # todos los demás Shorts de su tema, así que en vez de una
        # llamada independiente por cada uno (que además tiende a
        # converger siempre en los mismos hashtags "obvios"), se pide un
        # pool de variantes de una sola vez y se van repartiendo -- ver
        # generate_short_metadata_pool().
        return _live_pool_metadata(artist, track_title, genre, context)

    content_type_label = "Vídeo largo de YouTube (tema completo o LP)"
    hints = _HINTS["main"]

    user_prompt = USER_TEMPLATE.format(
        artist=artist,
        track_title=track_title,
        genre=genre,
        context=context,
        content_type_label=content_type_label,
        title_hint=hints["title"],
        description_hint=hints["description"],
    )

    return call_claude_json(
        SYSTEM_PROMPT, user_prompt,
        max_tokens=1800,
        model=MODEL,
    )


PLAYLIST_USER_TEMPLATE = """Genera la descripción de una lista de reproducción de
YouTube que reúne TODOS los temas de un álbum, en orden.

Artista: {artist}
Álbum: {lp_title}
Género/estilo: {genre}
Concepto/narrativa del álbum: {concept}

Devuelve un JSON con esta forma exacta:
{{
  "description": "string, 3-6 líneas: qué es el álbum, su concepto/atmósfera, y una llamada a la acción para escucharlo entero de principio a fin",
  "hashtags": ["#etiqueta1", "#etiqueta2", "#etiqueta3", "3-5 hashtags MÁXIMO y muy relevantes — pasarse de 5 hace que YouTube lo clasifique como spam"]
}}
"""


def generate_playlist_metadata(artist, lp_title, genre, concept):
    user_prompt = PLAYLIST_USER_TEMPLATE.format(
        artist=artist, lp_title=lp_title, genre=genre, concept=concept or "",
    )
    return call_claude_json(SYSTEM_PROMPT, user_prompt, max_tokens=800, model=MODEL)


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
