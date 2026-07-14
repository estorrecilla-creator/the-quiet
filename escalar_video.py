"""
escalar_video.py — asistente para dar más nitidez a un clip de vídeo
suelto con IA (Real-ESRGAN vía Video2X), por si algún clip de stock llega
justo de calidad. No forma parte del pipeline automático: es una
herramienta aparte para usar clip a clip, cuando tú decidas que uno lo
necesita — corre en local, gratis, pero necesita tener Video2X instalado
y una GPU con soporte Vulkan medianamente decente.

Instalación de Video2X: https://docs.video2x.org/installing/index.html

Uso:
    python escalar_video.py
"""

from pathlib import Path

from src.upscale import is_video2x_available, upscale_video


def _strip_quotes(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def ask_path(prompt):
    while True:
        raw = input(f"{prompt}: ").strip()
        value = _strip_quotes(raw)
        if value and Path(value).expanduser().exists():
            return str(Path(value).expanduser())
        print(f"  No encuentro el archivo: {value}")


def main():
    print("=== Escalar un clip de vídeo con IA (Video2X / Real-ESRGAN) ===\n")

    if not is_video2x_available():
        print(
            "No encuentro el programa 'video2x' en el PATH. Instálalo (gratis) "
            "desde https://docs.video2x.org/installing/index.html — necesita "
            "además una GPU con soporte Vulkan. Sin él, esta herramienta no "
            "puede continuar (el resto del pipeline funciona igual sin ella)."
        )
        return

    clip_path = ask_path("Ruta al clip de vídeo a escalar")
    scale_raw = input("¿Factor de escala? (2 o 4) [2]: ").strip()
    scale = int(scale_raw) if scale_raw else 2

    out_path = str(Path(clip_path).with_name(f"{Path(clip_path).stem}_x{scale}{Path(clip_path).suffix}"))
    print(f"-> Escalando con Video2X/Real-ESRGAN x{scale} (puede tardar, según tu GPU)...")
    upscale_video(clip_path, out_path, scale=scale)
    print(f"Listo: {out_path}")


if __name__ == "__main__":
    main()
