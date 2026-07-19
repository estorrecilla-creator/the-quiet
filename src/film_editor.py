"""
film_editor.py
Monta un vídeo con varios cortes reales de una película (de dominio
público, ya verificada) en vez de un único clip de fondo: detecta los
planos de la película, y para cada Short/vídeo genera un montaje propio
con cortes cuya duración varía según la energía del audio en ese tramo
(más energía = cortes más rápidos, menos energía = planos más largos),
mezclando primeros planos y planos generales donde se puede detectar.

Flujo:
1. `detect_scenes()` — detecta los cambios de plano de la película UNA
   vez (resultado cacheado en un .json junto a la película, tarda según
   la duración de la película pero no hay que repetirlo por cada tema).
2. `tag_scene_types()` — clasifica cada plano como "closeup" o "wide"
   con un heurístico ligero (cara detectada y grande en el fotograma
   central del plano = closeup).
3. `build_energy_driven_edit()` — para un tramo de audio [start, end],
   calcula una curva de energía y decide cuántos cortes hacen falta y de
   qué duración cada uno (más cortos en los picos de energía).
4. `render_edit()` — extrae y encadena esos planos con ffmpeg en un único
   vídeo de la duración exacta pedida, listo para usarse como portada de
   un Short/vídeo tal cual (ya no necesita más loop/zoompan).

No reutiliza el mismo plano de la película dos veces en todo el álbum
(vía `exclude_ranges`, igual que el resto del pipeline evita repetir
clips de stock).
"""

import json
import math
import random
import subprocess
import tempfile
from pathlib import Path

import librosa
import numpy as np

SCENE_CACHE_SUFFIX = ".scenes.json"


def detect_scenes(film_path: str, min_scene_len: float = 1.0, threshold: float = 0.35, cache_path: str = None):
    """
    Detecta cambios de plano con el filtro `select`+`scdet`/`scene` de
    ffmpeg (sin dependencias nuevas). Devuelve una lista de (start, end)
    en segundos. Cachea el resultado en `cache_path` (por defecto,
    `<película>.scenes.json`) para no repetir la detección en cada tema.
    """
    cache_path = cache_path or (film_path + SCENE_CACHE_SUFFIX)
    if Path(cache_path).exists():
        return json.loads(Path(cache_path).read_text(encoding="utf-8"))

    duration = _probe_duration(film_path)

    cmd = [
        "ffmpeg", "-i", film_path,
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    cut_times = [0.0]
    for line in result.stderr.splitlines():
        if "pts_time:" in line:
            try:
                t = float(line.split("pts_time:")[1].split()[0])
                cut_times.append(t)
            except (IndexError, ValueError):
                continue
    cut_times.append(duration)
    cut_times = sorted(set(cut_times))

    scenes = []
    for a, b in zip(cut_times, cut_times[1:]):
        if b - a >= min_scene_len:
            scenes.append((round(a, 2), round(b, 2)))

    Path(cache_path).write_text(json.dumps(scenes), encoding="utf-8")
    return scenes


def _probe_duration(path: str) -> float:
    cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def _extract_mid_frame(film_path: str, start: float, end: float, out_path: str):
    mid = (start + end) / 2
    cmd = ["ffmpeg", "-y", "-ss", str(mid), "-i", film_path, "-frames:v", "1", out_path]
    subprocess.run(cmd, capture_output=True, text=True)


def _is_closeup(frame_path: str, min_face_area_fraction: float = 0.12) -> bool:
    """Heurístico ligero: hay una cara detectada que ocupa una fracción
    grande del fotograma -> se trata como primer plano. Si la API de
    caras de mediapipe no está disponible en esta instalación (varía
    según la versión), se degrada a "no lo sé" (wide) en vez de fallar —
    es un heurístico de más, no algo de lo que dependa el montaje."""
    try:
        import mediapipe as mp
        from PIL import Image
    except ImportError:
        return False

    if not Path(frame_path).exists():
        return False

    try:
        img = Image.open(frame_path).convert("RGB")
        with mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5) as detector:
            result = detector.process(np.array(img))
            if not result.detections:
                return False
            best = max(
                result.detections,
                key=lambda d: d.location_data.relative_bounding_box.width * d.location_data.relative_bounding_box.height,
            )
            box = best.location_data.relative_bounding_box
            return (box.width * box.height) >= min_face_area_fraction
    except Exception:
        return False


def _has_motion(film_path: str, start: float, end: float, min_diff: float = 4.0) -> bool:
    """Heurístico: compara dos fotogramas dentro del plano (al 20% y al
    80% de su duración) — si apenas cambian, es un plano estático (p.ej.
    un cartel de texto/intertítulo de cine mudo), no imagen real en
    movimiento. Si no se puede comprobar, se asume que sí tiene
    movimiento (no se descarta un plano válido por error de sonda)."""
    dur = end - start
    t1 = start + dur * 0.2
    t2 = start + dur * 0.8
    with tempfile.TemporaryDirectory() as tmp:
        f1 = str(Path(tmp) / "a.jpg")
        f2 = str(Path(tmp) / "b.jpg")
        subprocess.run(["ffmpeg", "-y", "-ss", str(t1), "-i", film_path, "-frames:v", "1", f1], capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-ss", str(t2), "-i", film_path, "-frames:v", "1", f2], capture_output=True)
        if not Path(f1).exists() or not Path(f2).exists():
            return True
        try:
            from PIL import Image
            img1 = np.array(Image.open(f1).convert("L"), dtype=np.float32)
            img2 = np.array(Image.open(f2).convert("L"), dtype=np.float32)
            if img1.shape != img2.shape:
                return True
            return float(np.abs(img1 - img2).mean()) >= min_diff
        except Exception:
            return True


def tag_scene_types(film_path: str, scenes, cache_path: str = None):
    """Devuelve una lista de dicts
    [{"start", "end", "type": "closeup"|"wide", "static": bool}, ...].
    `static` marca planos sin movimiento real entre su inicio y su final
    (carteles de texto/intertítulos de cine mudo) para poder excluirlos
    del montaje — si no, con una película con muchos intertítulos el
    resultado final puede parecer una imagen fija en vez de un montaje.
    Cachea junto al resultado de `detect_scenes` para no re-analizar."""
    cache_path = cache_path or (film_path + ".scenetypes.v2.json")
    if Path(cache_path).exists():
        return json.loads(Path(cache_path).read_text(encoding="utf-8"))

    tagged = []
    with tempfile.TemporaryDirectory() as tmp:
        for start, end in scenes:
            frame_path = str(Path(tmp) / "frame.jpg")
            _extract_mid_frame(film_path, start, end, frame_path)
            scene_type = "closeup" if _is_closeup(frame_path) else "wide"
            static = not _has_motion(film_path, start, end)
            tagged.append({"start": start, "end": end, "type": scene_type, "static": static})

    Path(cache_path).write_text(json.dumps(tagged), encoding="utf-8")
    return tagged


def build_energy_driven_edit(
    audio_path: str, start: float, end: float, tagged_scenes,
    exclude_ranges: set, min_cut: float = 1.2, max_cut: float = 5.5,
    sr: int = 22050, used_scenes_out: list = None,
):
    """
    Decide la lista ordenada de cortes (planos + duración de cada uno)
    para cubrir exactamente `end - start` segundos de audio, con cortes
    más rápidos en los tramos de más energía. `exclude_ranges` es un set
    mutable de "start-end" ya usados (se actualiza in-place) — puede ser
    el pool global del álbum (para que cada tema use planos distintos a
    los demás) o un pool local de un solo tema (para que sus Shorts
    reutilicen los mismos planos que su vídeo principal en vez de gastar
    más planos del álbum). Si se pasa `used_scenes_out` (lista mutable),
    se le añade cada plano de `tagged_scenes` realmente usado (fresco o
    reutilizado), útil para luego construir ese pool local por tema.
    Devuelve una lista de dicts [{"start", "end", "cut_duration"}, ...]
    con planos de `tagged_scenes`.
    """
    y, _ = librosa.load(audio_path, sr=sr, offset=start, duration=end - start, mono=True)
    hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    rms_norm = rms / (rms.max() + 1e-9)

    total = end - start

    def _shuffled_pools(scenes):
        closeup = [s for s in scenes if s["type"] == "closeup"]
        wide = [s for s in scenes if s["type"] == "wide"]
        random.shuffle(closeup)
        random.shuffle(wide)
        return [closeup, wide]

    def _long_enough(s):
        return (s["end"] - s["start"]) >= min_cut

    # se descartan los planos estáticos (carteles/intertítulos) del
    # montaje: sin ellos el resultado se ve como cortes de película de
    # verdad en vez de una imagen fija cambiando de cartel en cartel.
    all_valid = [s for s in tagged_scenes if _long_enough(s) and not s.get("static", False)]
    if not all_valid:
        # si TODOS los planos válidos resultaran estáticos (poco probable
        # salvo película casi solo de texto), mejor usar esos que reventar.
        all_valid = [s for s in tagged_scenes if _long_enough(s)]
    if not all_valid:
        raise RuntimeError(
            "Ningún plano de la película llega a la duración mínima de corte "
            f"({min_cut}s) — prueba con una película con planos más largos, o "
            "baja min_cut."
        )

    fresh = [s for s in all_valid if f"{s['start']}-{s['end']}" not in exclude_ranges]
    pools = _shuffled_pools(fresh)
    pool_i = 0
    reused_any = False

    edit = []
    t = 0.0

    while t < total:
        frame_idx = min(int((t / total) * len(rms_norm)), len(rms_norm) - 1)
        energy = float(rms_norm[frame_idx]) if len(rms_norm) else 0.5
        # más energía -> corte más corto (más rápido); interpolación lineal inversa
        cut_duration = max_cut - energy * (max_cut - min_cut)
        cut_duration = min(cut_duration, total - t)
        if cut_duration < min_cut and edit:
            # último tramo demasiado corto para un plano nuevo: se alarga el anterior
            edit[-1]["cut_duration"] += cut_duration
            break

        pool = pools[pool_i % 2]
        if not pool:
            pool = pools[(pool_i + 1) % 2]
        if not pool:
            # Se acabaron los planos sin usar todavía — la película no tiene
            # planos suficientes para cubrir todo el álbum sin repetir ni
            # uno. Mejor reutilizar (de nuevo se prioriza variedad dentro de
            # lo posible, barajando otra vez) que reventar la generación.
            reused_any = True
            pools = _shuffled_pools(all_valid)
            pool = pools[pool_i % 2] or pools[(pool_i + 1) % 2]
        scene = pool.pop()
        pool_i += 1
        if used_scenes_out is not None:
            used_scenes_out.append(scene)

        key = f"{scene['start']}-{scene['end']}"
        exclude_ranges.add(key)
        scene_len = scene["end"] - scene["start"]
        used_len = min(cut_duration, scene_len)
        scene_offset = scene["start"] if scene_len <= used_len else scene["start"] + random.uniform(0, scene_len - used_len)

        edit.append({"start": scene_offset, "end": scene_offset + used_len, "cut_duration": used_len})
        t += used_len

    if reused_any:
        print(
            "   Aviso: la película no tiene planos suficientes para cubrir "
            "todo el álbum sin repetir ninguno — se han reutilizado algunos "
            "(mezclados de nuevo al azar, no es el mismo tramo seguido)."
        )

    return edit


def render_edit(
    film_path: str, edit, out_path: str, w: int = 1080, h: int = 1920, fps: int = 25,
    fade_duration: float = 0.4,
) -> str:
    """Extrae y encadena los planos de `edit` en un único vídeo de salida,
    escalado/recortado a (w, h), con la duración exacta de la suma de
    `cut_duration`.

    Nada de corte seco ni de disolución mezclando dos imágenes (efecto
    "montaje"): cada plano funde a negro por completo antes de que
    empiece el siguiente, con el aire retro/antiguo de las
    transiciones de cine clásico — nunca se ven dos escenas distintas
    superpuestas a la vez. `fade_duration` es el tiempo de fundido de
    entrada/salida de cada plano (se recorta solo si el plano es más
    corto que 2x ese tiempo, para no comerse todo el plano en el
    fundido)."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="film_edit_"))
    try:
        clip_paths = []
        for i, cut in enumerate(edit):
            clip_path = str(tmp_dir / f"cut_{i:03d}.mp4")
            duration = cut["cut_duration"]
            fd = min(fade_duration, max(duration / 2 - 0.02, 0.0))
            fade_filter = (
                f",fade=t=in:st=0:d={fd:.3f}:color=black,"
                f"fade=t=out:st={max(duration - fd, 0.0):.3f}:d={fd:.3f}:color=black"
                if fd > 0.02 else ""
            )
            cmd = [
                "ffmpeg", "-y", "-ss", str(cut["start"]), "-i", film_path,
                "-t", str(duration),
                "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1{fade_filter}",
                "-an", clip_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg no pudo extraer el corte {i}:\n{result.stderr[-1500:]}")
            clip_paths.append(clip_path)

        concat_list = tmp_dir / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{Path(p).resolve()}'" for p in clip_paths), encoding="utf-8"
        )
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg no pudo unir los cortes:\n{result.stderr[-1500:]}")
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return out_path
