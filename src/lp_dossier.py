"""
lp_dossier.py
Extrae de un documento de LP en texto libre (como el que describe todo el
concepto del álbum, tema a tema: título, letra, estilo/atmósfera...) los
datos estructurados que necesita el pipeline para generar automáticamente
el vídeo/Shorts/metadatos de cada tema: artista, nombre del LP, género, y
por cada tema su número, título, letra (tal cual, o None si es
instrumental) y contexto/atmósfera.

No hace falta seguir ninguna plantilla fija: Claude interpreta el
documento igual que lo haría una persona leyéndolo, así que puedes
escribirlo como te salga natural (es lo mismo que se hizo a mano para
"The Hollow Hour").
"""

import json

from src.anthropic_utils import call_claude_json

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """Eres un asistente que prepara el contenido de un LP musical para un
pipeline de generación de vídeo automático. Te paso un documento en texto libre
donde el artista describe su álbum: concepto general, y por cada tema su título,
letra (si la tiene) y notas de estilo/atmósfera/narrativa.

Tu trabajo es extraer esa información en JSON estructurado, SIN inventar ni
resumir nada:
- La letra de cada tema hay que reproducirla TAL CUAL aparece en el documento,
  palabra por palabra, línea por línea — es la letra real del artista, no la
  reescribas, no la resumas, no la "mejores".
- El "context" de cada tema es una descripción breve (2-4 frases) en español,
  pensada para generar imágenes/vídeo/metadatos de ese tema: mezcla el
  concepto/atmósfera general del LP con lo específico de ese tema si el
  documento lo detalla (tema narrativo, estado de ánimo, imágenes recurrentes).
- El "concept" es una descripción breve (2-4 frases) en español del concepto/
  narrativa/atmósfera general del ÁLBUM ENTERO (no de un tema en concreto),
  pensada para la descripción de la lista de reproducción del álbum. Aquí sí
  puedes describir la atmósfera, las influencias o comparar con otros
  artistas si el documento lo hace — este campo es solo para contexto
  interno, nunca se escribe en el archivo de audio.
- El "genre" es SOLO una etiqueta de género corta y normalizada — 1-3
  palabras, en formato estándar de catálogo musical (ej. "Progressive
  Rock", "Doom Folk", "Rock Alternativo"; si encajan dos, sepáralos con
  " / " como "Rock / Progressive Rock"). NUNCA una frase descriptiva, NUNCA
  nombres de otros artistas o bandas de referencia (aunque el documento
  mencione influencias como "con aire a Pink Floyd" — eso va en "concept",
  no en "genre"). Este campo se escribe tal cual en los metadatos del
  archivo de audio final, así que tiene que quedar limpio y publicable.
- Si un tema es instrumental (no tiene letra), "lyrics" debe ser null.
- Los temas van en el "number" que les corresponda según el documento (su
  posición/orden en el tracklist o álbum, empezando en 1).

Responde ÚNICAMENTE con JSON válido, sin texto adicional ni bloques de
markdown, con esta forma exacta:
{
  "artist": "nombre del artista/grupo",
  "lp_title": "nombre del LP/álbum",
  "genre": "etiqueta de género corta y normalizada, 1-3 palabras, sin nombres de otros artistas",
  "concept": "concepto/narrativa/atmósfera general del álbum en 2-4 frases",
  "tracks": [
    {"number": 1, "title": "...", "lyrics": "..." o null, "context": "..."},
    ...
  ]
}"""

USER_TEMPLATE = """Documento del LP:

{dossier_text}

Extrae el JSON estructurado según las instrucciones."""


def parse_lp_dossier(dossier_text: str) -> dict:
    user_prompt = USER_TEMPLATE.format(dossier_text=dossier_text)
    result = call_claude_json(SYSTEM_PROMPT, user_prompt, max_tokens=16000, model=MODEL)

    if not result.get("tracks"):
        raise ValueError("No se ha podido extraer ningún tema del documento del LP.")

    return result


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv
    load_dotenv()

    with open(sys.argv[1], encoding="utf-8") as f:
        text = f.read()

    data = parse_lp_dossier(text)
    print(json.dumps(data, indent=2, ensure_ascii=False))
