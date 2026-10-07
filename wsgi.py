"""WSGI entry point for production hosts (Render, Railway, Fly, a VPS).

    gunicorn -w 1 --threads 4 -b 0.0.0.0:$PORT wsgi:app

One worker is deliberate: the Whisper model costs ~200 MB of RAM when loaded,
so on a 512 MB instance a second worker would OOM.  Concurrency comes from the
threads -- transcription is C-level (ctranslate2) and releases the GIL.
"""

import os
import sys
import threading
import time

# app/ holds the modules (server, stt, politeness, translate) and is not a
# package, so it has to be on sys.path before any of them can be imported.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

import stt                                     # noqa: E402
from server import app                         # noqa: E402,F401  (re-exported)

_boot = time.time()
_ready = {"model": False, "error": None}


def _warm():
    """Load Whisper in the background so boot stays fast.

    Render fails a deploy if the health check does not answer in time, and a
    cold model download (~75 MB) can take longer than that window.
    """
    try:
        stt.get_model()
        _ready["model"] = True
    except Exception as exc:                      # pragma: no cover
        _ready["error"] = str(exc)


if os.environ.get("PRELOAD_MODEL", "1") != "0":
    threading.Thread(target=_warm, daemon=True).start()


@app.get("/api/ready")
def ready():
    """Deploy health check.  Answers immediately, reports model state."""
    return {
        "app": "ok",
        "uptime_s": round(time.time() - _boot, 1),
        "model": stt.DEFAULT_MODEL,
        "model_loaded": _ready["model"],
        "model_error": _ready["error"],
    }
