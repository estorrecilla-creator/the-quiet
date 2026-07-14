"""
cinematic_grade.py
Fragmento de filtro ffmpeg para un acabado discreto tipo "cine": viñeta
suave + grano fino + un ligero toque de color entre sombras y luces
(sombras algo más cálidas, luces algo más frías — la versión sutil del
clásico "teal & orange", sin pasarse). Pensado para aplicarse sobre la
capa de fondo (portada + estrella + persona), antes de las capas de
texto/UI (forma de onda, letra, marca de agua), para no ensuciar la
legibilidad del texto ni oscurecer sus esquinas con la viñeta.
"""


def cinematic_grade_filter(
    label: str,
    out_label: str,
    vignette_strength: str = "PI/6",
    grain_strength: int = 6,
    warm_shadows: float = 0.015,
    cool_highlights: float = 0.015,
) -> str:
    return (
        f"[{label}]vignette={vignette_strength},"
        f"noise=alls={grain_strength}:allf=t+u,"
        f"colorbalance=rs={warm_shadows}:bs=-{warm_shadows}:rh=-{cool_highlights}:bh={cool_highlights}"
        f"[{out_label}]"
    )
