"""
anthropic_utils.py
Llamada compartida a Claude para los sitios del pipeline que esperan un
único bloque JSON como respuesta (metadatos, prompts de imagen/vídeo,
extracción del dossier del LP). Dos problemas reales detectados
procesando un LP completo (cientos de llamadas seguidas, generando el
tema 2 al 12 de "The Hollow Hour" fallaron casi todos):

1. JSON mal formado: con descripciones largas de varias frases, Claude a
   veces mete un salto de línea suelto sin escapar dentro de una cadena
   ("Invalid control character") o dos comillas sin escapar cortan la
   cadena a mitad ("Unterminated string" / "Expecting value" más
   adelante). `json.loads(..., strict=False)` arregla el caso de los
   saltos de línea sin más; si aun así falla, se vuelve a pedir la
   respuesta entera (probabilístico: casi siempre sale bien a la
   segunda).
2. Picos de carga de la propia API de Anthropic (529 Overloaded): el
   SDK ya reintenta solo, pero con el margen por defecto (2) no siempre
   basta encadenando cientos de llamadas — se sube el límite.
"""

import json

import anthropic

# Margen generoso: generando un LP entero se encadenan cientos de
# llamadas seguidas, así que conviene aguantar más que el valor por
# defecto del SDK (2) ante un pico de carga puntual de la API (529).
CLIENT_MAX_RETRIES = 6


def call_claude_json(system_prompt: str, user_prompt: str, max_tokens: int, model: str, json_retries: int = 3):
    """
    Llama a Claude esperando JSON puro como respuesta (nada de texto ni
    bloques de markdown alrededor — ya se limpia por si acaso) y lo
    parsea. Si el JSON no se puede parsear, reintenta la llamada entera
    hasta `json_retries` veces antes de propagar el error.
    """
    client = anthropic.Anthropic(max_retries=CLIENT_MAX_RETRIES)

    last_error = None
    for attempt in range(1, json_retries + 1):
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        raw_text = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        try:
            # strict=False: tolera caracteres de control (saltos de línea
            # sueltos sin escapar) dentro de una cadena, la causa más
            # habitual de este fallo con descripciones de varias frases.
            return json.loads(raw_text, strict=False)
        except json.JSONDecodeError as e:
            last_error = e
            if attempt < json_retries:
                print(
                    f"   Aviso: respuesta de Claude con JSON mal formado "
                    f"(intento {attempt}/{json_retries}), reintentando..."
                )

    raise last_error
