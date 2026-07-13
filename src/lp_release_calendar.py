"""
lp_release_calendar.py
Calendario de lanzamiento de un LP completo, en singles escalonados:
para cada tema calcula cuándo hay que subirlo a DistroKid (con margen de
antelación) y a partir de cuándo se puede empezar a publicar su contenido
de YouTube (nunca antes de que esté disponible en streaming).

DistroKid no tiene API pública, así que la parte de DistroKid es siempre
manual — este módulo solo calcula las fechas para que sepas cuándo hacerlo
tú, no sube nada.
"""

import json
from datetime import date, timedelta
from pathlib import Path


def next_friday(d: date) -> date:
    """Devuelve el viernes siguiente (o el mismo día, si ya es viernes)."""
    days_ahead = (4 - d.weekday()) % 7  # Monday=0 ... Friday=4
    return d + timedelta(days=days_ahead)


def build_lp_calendar(
    track_names,
    first_release_date: date,
    cadence_days: int = 14,
    distrokid_lead_days: int = 30,
):
    """
    `track_names`: lista de nombres de tema, en el orden narrativo del LP.
    `first_release_date`: fecha de lanzamiento en streaming del primer
    tema (se ajusta al viernes siguiente si no lo es ya).
    `cadence_days`: días entre el lanzamiento de un tema y el siguiente.
    `distrokid_lead_days`: márgen de antelación con el que hay que subir
    cada tema a DistroKid antes de su fecha de lanzamiento.
    """
    release_date = next_friday(first_release_date)
    calendar = []
    for track in track_names:
        calendar.append({
            "track": track,
            "distrokid_submit_by": (release_date - timedelta(days=distrokid_lead_days)).isoformat(),
            "distrokid_release_date": release_date.isoformat(),
            "youtube_start_date": release_date.isoformat(),
        })
        release_date = release_date + timedelta(days=cadence_days)
    return calendar


def save_lp_calendar(calendar, out_path):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(calendar, f, ensure_ascii=False, indent=2)
    return out_path
