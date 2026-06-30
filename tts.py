#!/usr/bin/env python3
"""Stage 3.5 — text-to-speech (deterministic, best-effort).

Reads the spoken script the reasoning stage produced (/tmp/brief/audio_script.txt) and synthesizes
an MP3 via the Google Cloud Text-to-Speech REST API, authenticating with an Application Default
Credentials token (stdlib urllib only — no pip, corp-airlock safe). Writes /tmp/brief/brief.mp3.

Audio is a nice-to-have, NEVER a blocker: this exits 0 (skips) if the script is empty, gcloud/ADC
is unavailable, scopes are missing, or the API errors. The delivery stage attaches brief.mp3 only
if it exists. Voice override: $BRIEF_TTS_VOICE (default en-US-Neural2-D).
"""
import base64
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

OUT = Path(os.environ.get("BRIEF_TMP", "/tmp/brief"))
SCRIPT = OUT / "audio_script.txt"
MP3 = OUT / "brief.mp3"
VOICE = os.environ.get("BRIEF_TTS_VOICE", "en-US-Neural2-D")
ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"


def log(msg: str) -> None:
    print(f"tts: {msg}", file=sys.stderr)


def main() -> None:
    MP3.unlink(missing_ok=True)  # never deliver a stale mp3 from a previous run
    if not SCRIPT.exists():
        log("no audio_script.txt — skipping")
        return
    text = SCRIPT.read_text().strip()[:4800]  # API text cap is ~5000 bytes
    if not text:
        log("empty script — skipping")
        return
    try:
        token = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as e:  # gcloud missing / not on PATH
        log(f"no ADC token ({type(e).__name__}) — skipping")
        return
    if not token:
        log("empty ADC token (re-auth ADC?) — skipping")
        return

    cfg = {"audioEncoding": "MP3"}
    if "Journey" not in VOICE:           # Journey voices reject speakingRate
        cfg["speakingRate"] = 1.05
    body = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": "en-US", "name": VOICE},
        "audioConfig": cfg,
    }).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            audio = json.loads(r.read()).get("audioContent")
    except Exception as e:
        log(f"synthesize failed ({type(e).__name__}: {e}) — skipping")
        return
    if not audio:
        log("no audioContent in response — skipping")
        return
    MP3.write_bytes(base64.b64decode(audio))
    log(f"wrote {MP3} ({MP3.stat().st_size} bytes, voice {VOICE})")


if __name__ == "__main__":
    main()
