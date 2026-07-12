"""
lyrics_align.py
Sincroniza automáticamente una letra en texto plano (un archivo .txt, una
frase por línea) con el audio real, usando reconocimiento de voz local
(faster-whisper) para averiguar cuándo se canta cada palabra, y genera un
.srt listo para usar con lyrics.py / video_generator.py.

No es perfecto (el reconocimiento de voz cantada nunca lo es al 100%), pero
hace la mayor parte del trabajo: revisa el .srt generado y ajusta a mano
alguna línea suelta si hace falta.
"""

import difflib
import re
import tempfile

MODEL_SIZE = "small"


def _normalize(word: str) -> str:
    return re.sub(r"[^\wáéíóúñü]", "", word.lower(), flags=re.UNICODE)


def _load_lyrics_lines(text_path: str):
    with open(text_path, encoding="utf-8") as f:
        lines = [line.strip() for line in f]
    return [line for line in lines if line]


def _fill_gaps(word_times, n):
    known_idxs = [i for i, t in enumerate(word_times) if t is not None]
    if not known_idxs:
        raise RuntimeError(
            "No se pudo emparejar ninguna palabra de la letra con el audio reconocido."
        )

    first = known_idxs[0]
    if first > 0:
        t0 = word_times[first][0]
        step = t0 / max(first, 1)
        for i in range(first):
            word_times[i] = (max(0.0, i * step), max(0.0, (i + 1) * step))

    for a, b in zip(known_idxs, known_idxs[1:]):
        if b - a > 1:
            t_a = word_times[a][1]
            t_b = word_times[b][0]
            gap = max(t_b - t_a, 0.01)
            step = gap / (b - a)
            for k, i in enumerate(range(a + 1, b), start=1):
                word_times[i] = (t_a + step * (k - 1), t_a + step * k)

    last = known_idxs[-1]
    if last < n - 1:
        t_end = word_times[last][1]
        span = word_times[last][1] - word_times[known_idxs[0]][0]
        avg_dur = span / max(last - known_idxs[0] + 1, 1) if span > 0 else 0.3
        for k, i in enumerate(range(last + 1, n), start=1):
            word_times[i] = (t_end + avg_dur * (k - 1), t_end + avg_dur * k)


def align_lyrics(audio_path: str, lyrics_text_path: str, model_size: str = MODEL_SIZE):
    from faster_whisper import WhisperModel

    lines = _load_lyrics_lines(lyrics_text_path)
    if not lines:
        raise ValueError("El archivo de letra está vacío.")

    user_words = []
    user_word_line = []
    for li, line in enumerate(lines):
        for w in line.split():
            nw = _normalize(w)
            if nw:
                user_words.append(nw)
                user_word_line.append(li)

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, word_timestamps=True)

    whisper_words = []
    whisper_times = []
    for seg in segments:
        for w in seg.words:
            nw = _normalize(w.word)
            if nw:
                whisper_words.append(nw)
                whisper_times.append((w.start, w.end))

    if not whisper_words:
        raise RuntimeError("No se detectó voz en el audio para sincronizar la letra.")

    matcher = difflib.SequenceMatcher(None, user_words, whisper_words, autojunk=False)
    word_times = [None] * len(user_words)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            word_times[block.a + k] = whisper_times[block.b + k]

    _fill_gaps(word_times, len(user_words))

    line_times = []
    for li, line in enumerate(lines):
        idxs = [i for i, l in enumerate(user_word_line) if l == li]
        if not idxs:
            continue
        start = word_times[idxs[0]][0]
        end = word_times[idxs[-1]][1]
        line_times.append((start, end, line))

    return line_times


def _format_srt_time(t: float) -> str:
    t = max(t, 0.0)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(line_times, out_path: str, tail_padding: float = 0.3, min_gap: float = 0.15):
    entries = []
    for i, (start, end, text) in enumerate(line_times):
        padded_end = end + tail_padding
        if i + 1 < len(line_times):
            padded_end = min(padded_end, line_times[i + 1][0] - min_gap)
        padded_end = max(padded_end, start + 0.5)
        entries.append((start, padded_end, text))

    with open(out_path, "w", encoding="utf-8") as f:
        for i, (start, end, text) in enumerate(entries, start=1):
            f.write(f"{i}\n{_format_srt_time(start)} --> {_format_srt_time(end)}\n{text}\n\n")


def build_synced_srt(audio_path: str, lyrics_text_path: str, out_srt_path: str, model_size: str = MODEL_SIZE):
    line_times = align_lyrics(audio_path, lyrics_text_path, model_size=model_size)
    write_srt(line_times, out_srt_path)
    return out_srt_path


def resolve_lyrics_srt(audio_path: str, lyrics_path: str):
    """
    Si `lyrics_path` ya es un .srt, se usa tal cual. Si es un .txt (letra en
    texto plano, una frase por línea), se sincroniza automáticamente contra
    el audio y se genera un .srt temporal.
    """
    if lyrics_path is None:
        return None, False

    lower = lyrics_path.lower()
    if lower.endswith(".srt"):
        return lyrics_path, False

    if lower.endswith(".txt"):
        tmp = tempfile.NamedTemporaryFile(suffix=".srt", prefix="synced_lyrics_", delete=False)
        tmp.close()
        build_synced_srt(audio_path, lyrics_path, tmp.name)
        return tmp.name, True

    raise ValueError(
        "La letra debe ser un archivo .srt (ya sincronizado) o .txt "
        "(texto plano, se sincroniza automáticamente)."
    )
