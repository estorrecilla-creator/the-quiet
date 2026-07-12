"""
cover_sequence.py
Da vida a una o varias imágenes estáticas de portada con movimiento de
cámara (zoom in/out, paneo lateral/vertical) usando el filtro zoompan de
ffmpeg. El movimiento es lineal desde el primer fotograma hasta el último,
sutil, y con el progreso siempre limitado a [0,1] (si ffmpeg decodifica
algún fotograma de más al final de un input recortado con -t, el
movimiento se queda quieto en su posición final en vez de salirse de la
imagen — eso es lo que causaba el efecto de "parpadeo"/"aparece y
desaparece"). Con varias imágenes, cada una recibe un tipo de movimiento
distinto y se encadenan con una transición que también varía (fundido a
negro, fundido cruzado, barridos...) en vez de siempre la misma.
"""

MOVEMENTS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]

TRANSITIONS = ["fadeblack", "fade", "smoothleft", "smoothright", "circleclose", "dissolve"]

TRANSITION_DURATION = 1.8  # segundos de fundido entre imágenes


def build_movement_chain(
    movement: str,
    w: int,
    h: int,
    duration: float,
    fps: int = 25,
    zoom_amount: float = 0.05,
    pan_amount: float = 0.06,
) -> str:
    """
    Cadena de filtros (a partir de un input de vídeo/imagen) que aplica un
    movimiento de cámara lineal y sutil durante `duration` segundos.
    """
    total_frames = max(1, round(duration * fps))
    base = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},scale=3840:2160"
    # min(...,1): si por redondeo ffmpeg decodifica algún fotograma más de
    # los calculados, el progreso se queda clavado en 1 en vez de salirse
    # del rango válido (eso producía el parpadeo).
    progress = f"min(on/{total_frames}\\,1)"

    opts = {"d": "1", "s": f"{w}x{h}", "fps": str(fps)}

    if movement == "zoom_out":
        opts["z"] = f"'(1+{zoom_amount})-{zoom_amount}*{progress}'"
    elif movement in ("pan_left", "pan_right", "pan_up", "pan_down"):
        const_zoom = round(1.0 + pan_amount, 4)
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
        opts["z"] = f"'1+{zoom_amount}*{progress}'"

    zoompan_args = ":".join(f"{k}={v}" for k, v in opts.items())
    return f"{base},zoompan={zoompan_args},setsar=1"


def compute_segment_durations(total_duration: float, n_images: int, transition: float = TRANSITION_DURATION):
    """
    Duración "en bruto" que debe renderizarse por cada imagen para que,
    tras encadenarlas con transiciones que se solapan `transition`
    segundos entre cada dos, el resultado final dure `total_duration`.
    """
    if n_images <= 1:
        return [total_duration]
    extra = transition * (n_images - 1) / n_images
    seg = total_duration / n_images + extra
    return [seg] * n_images


def build_cover_sequence_filter(
    n_images: int,
    durations,
    w: int,
    h: int,
    fps: int,
    input_offset: int,
    out_label: str = "cover",
    transition: float = TRANSITION_DURATION,
    use_transition: bool = True,
):
    """
    Genera el fragmento de filtro que aplica un movimiento distinto a cada
    una de las `n_images` imágenes (inputs de ffmpeg consecutivos empezando
    en `input_offset`) y las une en un único stream `[out_label]`, con una
    transición (tipo distinto cada vez) entre cada dos si `use_transition`.
    Al final se fija la duración exacta a la suma "objetivo" (sin el
    solape de las transiciones) con `trim`+`tpad`, para que nunca quede ni
    un fotograma más corta ni más larga que el audio, evitando el
    desfase acumulado de la letra en temas con varias imágenes.
    """
    fragments = []
    seg_labels = []
    for i in range(n_images):
        movement = MOVEMENTS[i % len(MOVEMENTS)]
        chain = build_movement_chain(movement, w, h, durations[i], fps=fps)
        seg_label = f"seg{i}_{out_label}"
        fragments.append(f"[{input_offset + i}:v]{chain}[{seg_label}]")
        seg_labels.append(seg_label)

    if n_images == 1:
        fragments.append(f"[{seg_labels[0]}]null[{out_label}]")
        return ";".join(fragments)

    if not use_transition:
        joined = "".join(f"[{s}]" for s in seg_labels)
        fragments.append(joined + f"concat=n={n_images}:v=1:a=0[{out_label}]")
        return ";".join(fragments)

    target_duration = sum(durations) - transition * (n_images - 1)

    prev = seg_labels[0]
    cumulative = durations[0]
    for i in range(1, n_images):
        offset = max(cumulative - transition, 0)
        trans_type = TRANSITIONS[(i - 1) % len(TRANSITIONS)]
        joined_label = f"joined{i}_{out_label}" if i < n_images - 1 else f"{out_label}_raw"
        fragments.append(
            f"[{prev}][{seg_labels[i]}]xfade=transition={trans_type}:"
            f"duration={transition}:offset={offset:.3f}[{joined_label}]"
        )
        cumulative = cumulative + durations[i] - transition
        prev = joined_label

    # Fija la duración final exacta (por si el redondeo de las transiciones
    # deja el vídeo un pelín más corto o más largo de lo previsto).
    fragments.append(
        f"[{prev}]trim=duration={target_duration:.3f},setpts=PTS-STARTPTS,"
        f"tpad=stop_mode=clone:stop_duration={transition * 2:.3f}[{out_label}]"
    )

    return ";".join(fragments)
