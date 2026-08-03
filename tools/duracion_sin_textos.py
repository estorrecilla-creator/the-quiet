"""
duracion_sin_textos.py — informa de cuánto quedaría una película si se
quitaran las escenas de solo texto (carteles/intertítulos), SIN generar
ningún vídeo nuevo -- solo el cálculo. También puede simular qué pasaría
si además se recortara cada plano real que dure más de un máximo dado
(--cap-real SEGUNDOS) -- en cine mudo muchos planos se alargan más de lo
que la trama necesita, así que capar los más largos a un máximo razonable
acorta el conjunto sin borrar ninguna escena de la historia.

Reutiliza la misma detección de planos y el mismo heurístico de "plano
estático = cartel de texto" que ya usa el pipeline para montar Shorts/
vídeos (ver src/film_editor.py: detect_scenes + tag_scene_types), así que
si ya se generó contenido con esta película antes, el resultado sale casi
al instante (usa la caché ya guardada junto al archivo); si es la primera
vez, tarda lo que tarde analizar la película entera.

Uso:
    python tools/duracion_sin_textos.py "ruta\\a\\la\\pelicula.mp4"
    python tools/duracion_sin_textos.py "ruta\\a\\la\\pelicula.mp4" --cap-real 8
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.film_editor import detect_scenes, tag_scene_types

TOP_LONGEST_TO_SHOW = 15


def _format_duration(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}min {s}s"
    return f"{m}min {s}s"


def main():
    if len(sys.argv) < 2:
        print(f"Uso: python {Path(__file__).name} <ruta_a_la_pelicula> [--cap-real SEGUNDOS]")
        sys.exit(1)

    film_path = sys.argv[1]
    if not Path(film_path).exists():
        print(f"No encuentro el archivo: {film_path}")
        sys.exit(1)

    cap_real = None
    if "--cap-real" in sys.argv:
        cap_real = float(sys.argv[sys.argv.index("--cap-real") + 1])

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

    real_durations = sorted((s["end"] - s["start"] for s in real_scenes), reverse=True)
    print(f"Los {min(TOP_LONGEST_TO_SHOW, len(real_durations))} planos reales más largos (candidatos a recortar primero):")
    for d in real_durations[:TOP_LONGEST_TO_SHOW]:
        print(f"  {d:6.1f}s")

    if cap_real is not None:
        capped_duration = sum(min(s["end"] - s["start"], cap_real) for s in real_scenes)
        n_affected = sum(1 for s in real_scenes if (s["end"] - s["start"]) > cap_real)
        saved = real_duration - capped_duration
        print(f"""
Simulación con --cap-real {cap_real:.1f}s (cada plano real que dure más se recorta a ese máximo):
  Planos afectados: {n_affected} de {len(real_scenes)}
  Duración de los planos reales tras el recorte: {_format_duration(capped_duration)}
  Tiempo ahorrado: {_format_duration(saved)}
  Duración total del vídeo final (planos reales recortados + rótulos nuevos, sin contar interludios): {_format_duration(capped_duration + text_duration)}
""")


if __name__ == "__main__":
    main()
