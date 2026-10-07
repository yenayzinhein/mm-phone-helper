#!/usr/bin/env python3
"""Copy the Whisper model into the repo so a deploy never downloads it.

Why this exists
---------------
Render's **Free** plan cannot attach a persistent disk (official docs:
"Free web services don't support: Persistent disks") and its filesystem is
ephemeral -- everything written at runtime is wiped whenever the service spins
down after 15 idle minutes.  A model downloaded on first request would be
re-downloaded (75 MB) on *every* cold start, on top of the ~60 s spin-up.
Unusable mid-phone-call.

So: ship the model with the code.  75 MB, under GitHub's 100 MB per-file hard
limit, so no Git LFS is needed.  Measured on this repo: loading from the
bundled directory takes 0.4 s versus a full download.

    python3 fetch_model.py            # -> models/tiny.en/  (75 MB, commit this)
    python3 fetch_model.py base.en    # -> models/base.en/  (~145 MB, do NOT commit)

On a **paid** plan, skip this and use a persistent disk instead
(render-paid.yaml) -- that keeps the repo small.

Note on method: `ctranslate2.Whisper` has no `.save()`, so this resolves the
Hugging Face cache snapshot and copies it with symlinks dereferenced.  The
result is a plain model directory that `WhisperModel(path)` loads directly.
"""

from __future__ import annotations

import glob
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "app"))

import stt  # noqa: E402

GITHUB_FILE_LIMIT = 100 * 1024 * 1024


def _resolve_snapshot(name: str) -> str:
    """Find the HF cache snapshot dir for `name`."""
    root = os.path.join(stt.DOWNLOAD_ROOT, f"models--Systran--faster-whisper-{name}",
                        "snapshots")
    hits = sorted(glob.glob(os.path.join(root, "*")))
    hits = [h for h in hits if os.path.isdir(h)]
    if not hits:
        raise SystemExit(f"no cached snapshot for {name!r} under {root} -- "
                         "run the app once so it downloads, then retry.")
    return hits[-1]


def main(name: str = stt.DEFAULT_MODEL) -> str:
    if name not in stt.AVAILABLE:
        raise SystemExit(f"unknown model {name!r}; choose from {stt.AVAILABLE}")

    src = _resolve_snapshot(name)
    dest = os.path.join(HERE, "models", name)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    # copytree(symlinks=False) dereferences, so the blobs become real files
    shutil.copytree(src, dest)
    print(f"copied {src}\n     -> {dest}")

    files = [(os.path.getsize(os.path.join(r, f)), os.path.join(r, f))
             for r, _, fs in os.walk(dest) for f in fs]
    total = sum(sz for sz, _ in files)
    print(f"size: {total / 1024 / 1024:.0f} MB across {len(files)} files")

    over = [p for sz, p in files if sz > GITHUB_FILE_LIMIT]
    if over:
        for p in over:
            print(f"WARNING: {p} exceeds GitHub's 100 MB limit -- use a paid "
                  "plan with a persistent disk instead of committing this.")
    else:
        print("under GitHub's 100 MB per-file limit -> safe to commit")

    # prove it loads straight from the committed directory
    from faster_whisper import WhisperModel
    probe = WhisperModel(dest, device="cpu", compute_type="int8")
    print("verified: loads from the bundled path ->", type(probe).__name__)
    return dest


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else stt.DEFAULT_MODEL)
