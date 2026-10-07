"""Whisper speech-to-text, lazily loaded and thread-safe.

`tiny.en` (~75 MB, int8) is the right default for a 2-core phone-call helper:
it loads in a couple of seconds and transcribes a short call clip quickly.

Audio is decoded with PyAV *directly* into a float32 numpy array instead of
handing faster-whisper a filename.  Reason: `faster_whisper.audio.decode_audio`
passes `metadata_errors="ignore"` to `av.open()`, which PyAV >= 16 no longer
accepts -- every upload failed with
`open() got an unexpected keyword argument 'metadata_errors'`.  Decoding here
keeps the app working across PyAV versions.
"""

from __future__ import annotations

import os
import threading

import numpy as np

_MODEL_CACHE: dict[str, object] = {}
_LOCK = threading.Lock()
DOWNLOAD_ROOT = os.environ.get(
    "WHISPER_ROOT", os.path.expanduser("~/.cache/whisper")
)

AVAILABLE = ["tiny.en", "base.en"]
DEFAULT_MODEL = "tiny.en"
SAMPLE_RATE = 16000


def model_path(name: str = DEFAULT_MODEL) -> str | None:
    """Path to a model bundled inside the repo, if one was committed.

    Render's Free plan cannot attach a persistent disk, so anything written at
    runtime is wiped on every spin-down -- including a downloaded model.  The
    workaround is to ship the model in the repo itself (see fetch_model.py).
    """
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         os.pardir, "models", name)
    return os.path.abspath(local) if os.path.isdir(local) else None


def get_model(name: str = DEFAULT_MODEL):
    """Load (once) and return a faster-whisper model.

    Uses the bundled copy when present, otherwise downloads into DOWNLOAD_ROOT.
    """
    if name not in AVAILABLE:
        name = DEFAULT_MODEL
    with _LOCK:
        if name not in _MODEL_CACHE:
            from faster_whisper import WhisperModel  # heavy, import lazily
            bundled = model_path(name)
            if bundled:
                _MODEL_CACHE[name] = WhisperModel(
                    bundled, device="cpu", compute_type="int8",
                )
            else:
                _MODEL_CACHE[name] = WhisperModel(
                    name, device="cpu", compute_type="int8",
                    download_root=DOWNLOAD_ROOT,
                )
        return _MODEL_CACHE[name]


def decode_audio(path: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Decode any container ffmpeg understands -> mono float32 @ `sr`."""
    import av

    chunks: list[np.ndarray] = []
    with av.open(path, mode="r") as container:
        container.streams.audio[0].thread_type = "AUTO"
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sr)
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                arr = out.to_ndarray()
                if arr.size:
                    chunks.append(arr.reshape(-1))
        for out in resampler.resample(None):        # flush
            arr = out.to_ndarray()
            if arr.size:
                chunks.append(arr.reshape(-1))

    if not chunks:
        raise ValueError("no audio stream found in the uploaded file")

    audio = np.concatenate(chunks).astype(np.float32) / 32768.0
    return np.clip(audio, -1.0, 1.0)


def transcribe(path: str, model_name: str = DEFAULT_MODEL, language: str = "en") -> dict:
    """Transcribe an audio file -> {"text", "segments", "language", "duration"}"""
    model = get_model(model_name)
    audio = decode_audio(path)

    kwargs = {"beam_size": 1, "vad_filter": True}
    if language:
        kwargs["language"] = language
    segments, info = model.transcribe(audio, **kwargs)

    segs, chunks = [], []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        chunks.append(text)
        segs.append({"start": round(seg.start, 2), "end": round(seg.end, 2),
                     "text": text})
    return {
        "text": " ".join(chunks).strip(),
        "segments": segs,
        "language": getattr(info, "language", language) or language,
        "duration": round(len(audio) / SAMPLE_RATE, 2),
    }
