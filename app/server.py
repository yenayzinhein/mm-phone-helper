"""Flask app: English audio -> transcript -> polite Burmese answer.

Run:  python3 server.py            (binds 0.0.0.0:5000)
"""

from __future__ import annotations

import os
import tempfile
import traceback

from flask import Flask, jsonify, request

import politeness
import stt
from translate import translate_to_polite

# Upload ceiling. 25 MB locally; hosted instances run on ~512 MB RAM and
# decoding a large file can spike past that, so MAX_AUDIO_MB lets a deploy
# lower it without touching code.
MAX_AUDIO_BYTES = int(os.environ.get("MAX_AUDIO_MB", "25")) * 1024 * 1024
ALLOWED_EXT = {".wav", ".webm", ".ogg", ".m4a", ".mp3", ".mp4", ".aac", ".flac", ".oga"}

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = MAX_AUDIO_BYTES


def _gender():
    g = (request.values.get("gender") or politeness.MALE).lower()
    return politeness.FEMALE if g.startswith("f") else politeness.MALE


@app.get("/")
def index():
    from flask import render_template
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "model": stt.DEFAULT_MODEL,
        "model_loaded": bool(stt._MODEL_CACHE),
        "models": stt.AVAILABLE,
    })


@app.get("/api/phrasebook")
def api_phrasebook():
    return jsonify({"gender": _gender(), "rows": politeness.phrasebook(_gender())})


@app.post("/api/polish")
def api_polish():
    """Burmese in -> polite Burmese out."""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    return jsonify({"input": text, **politeness.to_polite(text, _gender())})


@app.post("/api/translate")
def api_translate():
    """English in -> polite Burmese answer."""
    data = request.get_json(silent=True) or {}
    english = (data.get("text") or "").strip()
    if not english:
        return jsonify({"error": "text is required"}), 400
    online = str(data.get("online", "1")) not in ("0", "false", "no")
    return jsonify(translate_to_polite(english, _gender(), online=online))


@app.post("/api/transcribe")
def api_transcribe():
    """Audio file in -> {transcript, polite Burmese}."""
    f = request.files.get("audio")
    if f is None or not f.filename:
        return jsonify({"error": "no audio uploaded"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"error": f"unsupported audio type: {ext}"}), 400

    model_name = (request.values.get("model") or stt.DEFAULT_MODEL)
    if model_name not in stt.AVAILABLE:
        model_name = stt.DEFAULT_MODEL

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        f.save(tmp.name)
        tmp.close()
        result = stt.transcribe(tmp.name, model_name)
    except Exception as exc:                      # never 500 on the user's call
        traceback.print_exc()
        return jsonify({"error": f"transcription failed: {exc}"}), 500
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    english = result["text"]
    answer = translate_to_polite(english, _gender()) if english else None
    return jsonify({"transcript": english, "segments": result["segments"],
                    "duration": result["duration"], "model": model_name,
                    "answer": answer})


@app.errorhandler(413)
def too_big(_):
    limit = MAX_AUDIO_BYTES // (1024 * 1024)
    return jsonify({"error": f"audio file too large (max {limit} MB)"}), 413


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    # warm the model so the first recording is not slow
    try:
        stt.get_model()
        print("whisper model ready:", stt.DEFAULT_MODEL)
    except Exception as exc:
        print("WARNING: could not preload whisper:", exc)
    app.run(host="0.0.0.0", port=port, threaded=True)
