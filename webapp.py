"""
webapp.py — interfaz web para generar contenido desde el móvil, sin terminal.

Uso local:
    export ANTHROPIC_API_KEY=sk-ant-...
    export APP_PASSWORD=algo-secreto
    python webapp.py

Para desplegarlo y poder usarlo desde el iPhone, ver README.md
(sección "Web app / uso desde el móvil").
"""

import os
import uuid
import threading
import traceback
from pathlib import Path
from functools import wraps

from dotenv import load_dotenv

load_dotenv()

from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template,
    send_from_directory,
    abort,
    flash,
)
from werkzeug.utils import secure_filename

from main import process_track

APP_PASSWORD = os.environ.get("APP_PASSWORD")
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("output")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_AUDIO = {"mp3", "wav"}
ALLOWED_IMAGE = {"jpg", "jpeg", "png"}

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24).hex())

# Estado de los trabajos en memoria: job_id -> dict(status, title, out_dir, files, error)
jobs = {}


def _ext_ok(filename, allowed):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if APP_PASSWORD and not session.get("authed"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if not APP_PASSWORD:
        session["authed"] = True
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session["authed"] = True
            return redirect(request.args.get("next") or url_for("index"))
        error = "Contraseña incorrecta."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["GET"])
@login_required
def index():
    return render_template(
        "index.html", api_key_set=bool(os.environ.get("ANTHROPIC_API_KEY"))
    )


def _run_job(job_id, audio_path, cover_path, artist, title, genre, context, n_shorts):
    job = jobs[job_id]
    try:
        job["status"] = "processing"
        out_dir = process_track(
            str(audio_path),
            str(cover_path),
            artist,
            title,
            genre,
            context,
            n_shorts,
            str(OUTPUT_DIR),
        )
        job["out_dir"] = str(out_dir)
        job["files"] = sorted(p.name for p in Path(out_dir).iterdir())
        job["status"] = "done"
    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
        job["trace"] = traceback.format_exc()


@app.route("/generar", methods=["POST"])
@login_required
def generar():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        flash("Falta ANTHROPIC_API_KEY en el servidor. Configúrala antes de generar contenido.")
        return redirect(url_for("index"))

    audio = request.files.get("audio")
    cover = request.files.get("cover")
    artist = request.form.get("artist", "").strip()
    title = request.form.get("title", "").strip()
    genre = request.form.get("genre", "").strip()
    context = request.form.get("context", "").strip()
    try:
        n_shorts = int(request.form.get("shorts", 3))
    except ValueError:
        n_shorts = 3

    if not audio or not audio.filename or not _ext_ok(audio.filename, ALLOWED_AUDIO):
        flash("Sube un audio .mp3 o .wav válido.")
        return redirect(url_for("index"))
    if not cover or not cover.filename or not _ext_ok(cover.filename, ALLOWED_IMAGE):
        flash("Sube una portada .jpg o .png válida.")
        return redirect(url_for("index"))
    if not all([artist, title, genre, context]):
        flash("Rellena artista, título, género y contexto.")
        return redirect(url_for("index"))

    job_id = uuid.uuid4().hex[:12]
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    audio_path = job_dir / secure_filename(audio.filename)
    cover_path = job_dir / secure_filename(cover.filename)
    audio.save(audio_path)
    cover.save(cover_path)

    jobs[job_id] = {"status": "queued", "title": title}
    thread = threading.Thread(
        target=_run_job,
        args=(job_id, audio_path, cover_path, artist, title, genre, context, n_shorts),
        daemon=True,
    )
    thread.start()

    return redirect(url_for("estado", job_id=job_id))


@app.route("/estado/<job_id>")
@login_required
def estado(job_id):
    job = jobs.get(job_id)
    if not job:
        abort(404)
    return render_template("estado.html", job_id=job_id, job=job)


@app.route("/descargar/<job_id>/<path:filename>")
@login_required
def descargar(job_id, filename):
    job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        abort(404)
    out_dir = Path(job["out_dir"]).resolve()
    return send_from_directory(out_dir, filename, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
