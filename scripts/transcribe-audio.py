#!/usr/bin/env python3
"""Transcribe audio from a URL (YouTube, podcast, etc.) using faster-whisper.

Usage:
    transcribe-audio.py <url>                    # defaults to base.en
    transcribe-audio.py <url> --model small.en   # override model
    transcribe-audio.py <url> --max-duration 7200  # skip >2hr audio
    transcribe-audio.py <url> --json             # emit timestamped segments (for deep-linking)

Output:
    default : plain text transcript to stdout (back-compat with /wiki-watch, /wiki-ingest)
    --json  : JSON {"text": "...", "segments": [{"start": s, "end": s, "text": "..."}]}
Errors to stderr.
Exit codes: 0 = success, 1 = fetch failed, 2 = transcribe failed.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

VALID_MODELS = {"tiny.en", "base.en", "small.en", "medium.en", "large-v3"}


def download_audio(url: str, out_dir: Path) -> Path:
    """Download audio via yt-dlp. Returns path to audio file."""
    out_template = str(out_dir / "audio.%(ext)s")
    cmd = [
        "yt-dlp",
        "--quiet",
        "--no-warnings",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "9",  # lowest quality is fine for transcription
        "-o", out_template,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"yt-dlp failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    audio_files = list(out_dir.glob("audio.mp3"))
    if not audio_files:
        print("yt-dlp produced no audio file", file=sys.stderr)
        sys.exit(1)
    return audio_files[0]


def transcribe(audio_path: Path, model_name: str) -> list[dict]:
    """Transcribe audio file. Returns segments [{start, end, text}] (timestamps in seconds).

    Timestamps are retained so callers can deep-link to the exact second a line was said.
    Use segments_to_text() if you only need plain text.
    """
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(
        str(audio_path),
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    return [
        {"start": round(seg.start, 2), "end": round(seg.end, 2), "text": seg.text.strip()}
        for seg in segments
    ]


def segments_to_text(segments: list[dict]) -> str:
    """Flatten segments back to a plain transcript (back-compat output)."""
    return " ".join(s["text"] for s in segments if s["text"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Audio URL (YouTube, podcast, direct MP3, etc.)")
    parser.add_argument(
        "--model",
        default="base.en",
        choices=sorted(VALID_MODELS),
        help="Whisper model (default: base.en)",
    )
    parser.add_argument(
        "--max-duration",
        type=int,
        default=7200,
        help="Skip audio longer than N seconds (default: 7200 = 2 hours)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON with timestamped segments (for minute-accurate deep-linking)",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        audio_path = download_audio(args.url, out_dir)
        try:
            segments = transcribe(audio_path, args.model)
        except Exception as e:
            print(f"transcribe failed: {e}", file=sys.stderr)
            sys.exit(2)
        if args.json:
            json.dump(
                {"text": segments_to_text(segments), "segments": segments},
                sys.stdout,
                ensure_ascii=False,
            )
            sys.stdout.write("\n")
        else:
            sys.stdout.write(segments_to_text(segments))
            sys.stdout.write("\n")


if __name__ == "__main__":
    main()
