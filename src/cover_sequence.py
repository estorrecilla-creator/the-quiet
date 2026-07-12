"""
cover_sequence.py
Da vida a una o varias imágenes estáticas de portada con movimiento de
cámara (zoom in/out, paneo lateral/vertical) usando el filtro zoompan de
ffmpeg. Con varias imágenes, cada una recibe un tipo de movimiento distinto
(se van repitiendo en ciclo) y se encadenan en el vídeo con `concat`.
"""

MOVEMENTS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]


def build_movement_chain(movement: str, w: int, h: int, duration: float, fps: int = 25, zoom_amount: float = 0.12) -> str:
    """
    Cadena de filtros (a partir de un input de vídeo/imagen) que aplica un
    movimiento de cámara suave durante `duration` segundos. Ni tan rápido
    que maree ni tan sutil que no se note.
    """
    total_frames = max(1, round(duration * fps))
    zmax = round(1.0 + zoom_amount, 4)
    step = round(zoom_amount / total_frames, 6)
    base = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},scale=3840:2160"

    opts = {"d": "1", "s": f"{w}x{h}", "fps": str(fps)}

    if movement == "zoom_out":
        opts["z"] = f"'if(eq(on,0),{zmax},max(zoom-{step},1.0))'"
    elif movement in ("pan_left", "pan_right", "pan_up", "pan_down"):
        const_zoom = round(1.0 + zoom_amount / 2, 4)
        progress = f"(on/{total_frames})"
        opts["z"] = str(const_zoom)
        if movement == "pan_left":
            opts["x"] = f"'(iw-ow)*(1-{progress})'"
            opts["y"] = "'(ih-oh)/2'"
        elif movement == "pan_right":
            opts["x"] = f"'(iw-ow)*{progress}'"
            opts["y"] = "'(ih-oh)/2'"
        elif movement == "pan_up":
            opts["x"] = "'(iw-ow)/2'"
            opts["y"] = f"'(ih-oh)*(1-{progress})'"
        else:
            opts["x"] = "'(iw-ow)/2'"
            opts["y"] = f"'(ih-oh)*{progress}'"
    else:  # zoom_in y valor por defecto
        opts["z"] = f"'min(zoom+{step},{zmax})'"

    zoompan_args = ":".join(f"{k}={v}" for k, v in opts.items())
    return f"{base},zoompan={zoompan_args},setsar=1"


def build_cover_sequence_filter(n_images: int, durations, w: int, h: int, fps: int, input_offset: int, out_label: str = "cover"):
    """
    Genera el fragmento de filtro que aplica un movimiento distinto a cada
    una de las `n_images` imágenes (inputs de ffmpeg consecutivos empezando
    en `input_offset`) y las concatena en un único stream `[out_label]`.
    """
    fragments = []
    seg_labels = []
    for i in range(n_images):
        movement = MOVEMENTS[i % len(MOVEMENTS)]
        chain = build_movement_chain(movement, w, h, durations[i], fps=fps)
        seg_label = f"seg{i}"
        fragments.append(f"[{input_offset + i}:v]{chain}[{seg_label}]")
        seg_labels.append(f"[{seg_label}]")

    concat = "".join(seg_labels) + f"concat=n={n_images}:v=1:a=0[{out_label}]"
    fragments.append(concat)
    return ";".join(fragments)
