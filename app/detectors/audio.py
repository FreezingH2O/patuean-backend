"""Transcode arbitrary uploaded audio (webm/opus from the browser, or an uploaded
mp3/m4a/etc.) to 16 kHz mono WAV, which the anti-spoof and ASR APIs accept.

Uses the ffmpeg binary bundled by imageio-ffmpeg, so no system ffmpeg install is
needed (works locally and in Vercel's /tmp-writable serverless sandbox).
"""

import os
import shutil
import subprocess
import tempfile


def _resolve_ffmpeg() -> str:
    """Find a usable ffmpeg regardless of how the server was launched.

    imageio_ffmpeg normally returns an absolute path to a bundled binary, but in
    some environments (e.g. this conda env) it returns the bare name "ffmpeg",
    which only works if the launcher's PATH happens to include it. A server
    started from GUI/conda often has a minimal PATH without Homebrew, so we fall
    back to shutil.which and then well-known absolute locations.
    """
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        exe = get_ffmpeg_exe()
        if exe and os.path.isabs(exe) and os.path.exists(exe):
            return exe
    except Exception:
        pass

    found = shutil.which("ffmpeg")
    if found:
        return found

    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if os.path.exists(candidate):
            return candidate

    # Last resort: the bare name, letting subprocess raise a clear error if absent.
    return "ffmpeg"


FFMPEG = _resolve_ffmpeg()


def to_wav(audio_bytes: bytes) -> bytes:
    # Write input to a temp file (matroska/webm demuxing needs a seekable source).
    with tempfile.NamedTemporaryFile(suffix=".input") as src:
        src.write(audio_bytes)
        src.flush()
        proc = subprocess.run(
            [FFMPEG, "-y", "-i", src.name, "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1"],
            capture_output=True,
        )
    if proc.returncode != 0 or not proc.stdout:
        detail = proc.stderr.decode(errors="ignore")[-400:]
        raise RuntimeError(f"Audio transcode failed: {detail}")
    return proc.stdout
