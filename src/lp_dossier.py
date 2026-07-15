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

import anthropic

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
  pensada para la descripción de la lista de reproducción del álbum.
- Si un tema es instrumental (no tiene letra), "lyrics" debe ser null.
- Los temas van en el "number" que les corresponda según el documento (su
  posición/orden en el tracklist o álbum, empezando en 1).

Responde ÚNICAMENTE con JSON válido, sin texto adicional ni bloques de
markdown, con esta forma exacta:
{
  "artist": "nombre del artista/grupo",
  "lp_title": "nombre del LP/álbum",
  "genre": "género/estilo general en 1-2 frases",
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
    client = anthropic.Anthropic()

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": USER_TEMPLATE.format(dossier_text=dossier_text)}],
    )

    raw_text = "".join(
        block.text for block in response.content if block.type == "text"
    )
    raw_text = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    result = json.loads(raw_text)

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
