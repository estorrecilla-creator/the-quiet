"""
duracion_sin_textos.py — informa de cuánto quedaría una película si se
quitaran las escenas de solo texto (carteles/intertítulos), SIN generar
ningún vídeo nuevo -- solo el cálculo.

Reutiliza la misma detección de planos y el mismo heurístico de "plano
estático = cartel de texto" que ya usa el pipeline para montar Shorts/
vídeos (ver src/film_editor.py: detect_scenes + tag_scene_types), así que
si ya se generó contenido con esta película antes, el resultado sale casi
al instante (usa la caché ya guardada junto al archivo); si es la primera
vez, tarda lo que tarde analizar la película entera.

Uso:
    python tools/duracion_sin_textos.py "ruta\\a\\la\\pelicula.mp4"
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.film_editor import detect_scenes, tag_scene_types


def _format_duration(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}min {s}s"
    return f"{m}min {s}s"


def main():
    if len(sys.argv) < 2:
        print(f"Uso: python {Path(__file__).name} <ruta_a_la_pelicula>")
        sys.exit(1)

    film_path = sys.argv[1]
    if not Path(film_path).exists():
        print(f"No encuentro el archivo: {film_path}")
        sys.exit(1)

    print(f"-> Analizando planos de {Path(film_path).name} (usa la caché si ya existe)...")
    scenes = detect_scenes(film_path)
    tagged = tag_scene_types(film_path, scenes)

    text_scenes = [s for s in tagged if s.get("static")]
    real_scenes = [s for s in tagged if not s.get("static")]

    total_duration = sum(s["end"] - s["start"] for s in tagged)
    text_duration = sum(s["end"] - s["start"] for s in text_scenes)
    real_duration = sum(s["end"] - s["start"] for s in real_scenes)

    pct_text = (text_duration / total_duration * 100) if total_duration else 0
    pct_real = 100 - pct_text

    print(f"""
Planos totales detectados: {len(tagged)}
Duración total analizada:  {_format_duration(total_duration)}

Planos de solo texto/cartel (estáticos): {len(text_scenes)}
  Duración: {_format_duration(text_duration)} ({pct_text:.1f}% del total)

Planos con imagen real (lo que quedaría): {len(real_scenes)}
  Duración: {_format_duration(real_duration)} ({pct_real:.1f}% del total)
""")


if __name__ == "__main__":
    main()
