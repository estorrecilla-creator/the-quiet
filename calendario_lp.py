"""
calendario_lp.py — asistente para calcular el calendario de lanzamiento de
un LP completo en singles escalonados: cuándo subir cada tema a DistroKid
(con margen de antelación) y a partir de cuándo puede empezar a publicarse
su contenido de YouTube (nunca antes que en streaming).

DistroKid no tiene API pública — este asistente solo calcula fechas, no
sube nada a ningún sitio. Guarda el resultado para que lo sigas a mano
(DistroKid) y lo uses como fecha de inicio en programar_youtube.py.

Uso:
    python calendario_lp.py
"""

from datetime import date, datetime
from pathlib import Path

from src.lp_release_calendar import build_lp_calendar, save_lp_calendar, next_friday


def _strip_quotes(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def ask(prompt, default=None, required=True):
    suffix = f" [{default}]" if default else ""
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        value = _strip_quotes(raw) if raw else default
        if value or not required:
            return value
        print("  Este dato es obligatorio.")


def main():
    print("=== Calendario de lanzamiento del LP ===\n")

    nombre_lp = ask("Nombre del LP (para guardar el calendario)")
    print("Escribe el nombre de cada tema, en orden narrativo, uno por línea.")
    print("Deja una línea en blanco para terminar.")
    tracks = []
    while True:
        line = input(f"  Tema {len(tracks) + 1}: ").strip()
        if not line:
            break
        tracks.append(line)
    if not tracks:
        print("No se ha indicado ningún tema.")
        return

    fecha_raw = ask("Fecha del primer lanzamiento (dd/mm/aaaa)")
    fecha = datetime.strptime(fecha_raw, "%d/%m/%Y").date()
    ajustada = next_friday(fecha)
    if ajustada != fecha:
        print(f"  (Ajustada al viernes siguiente: {ajustada.strftime('%d/%m/%Y')} — mejor para listas editoriales)")

    cadence = int(ask("Días entre el lanzamiento de un tema y el siguiente", "14"))
    lead = int(ask("Días de antelación necesarios para subir a DistroKid antes del lanzamiento", "30"))

    calendar = build_lp_calendar(tracks, fecha, cadence_days=cadence, distrokid_lead_days=lead)

    print("\n--- Calendario propuesto ---")
    for i, item in enumerate(calendar, start=1):
        print(f"{i:2}. {item['track']}")
        print(f"      Subir a DistroKid antes de: {item['distrokid_submit_by']}")
        print(f"      Lanzamiento en streaming:   {item['distrokid_release_date']}")
        print(f"      YouTube puede empezar el:   {item['youtube_start_date']}")

    out_dir = Path("lp_content") / nombre_lp.replace(" ", "_")
    out_path = save_lp_calendar(calendar, out_dir / "calendario_lanzamiento.json")
    print(f"\nGuardado en: {out_path}")
    print("Usa la fecha 'YouTube puede empezar el' de cada tema como fecha del "
          "primer envío en programar_youtube.py cuando llegue el momento.")


if __name__ == "__main__":
    main()
