#!/usr/bin/env python3
"""Minute-accurate deep-linking for the AI Daily Brief. Pure stdlib (runs anywhere).

Subcommands:
  match <segments.json> "<quote>" [--video-id ID]
      Fuzzy-match a quoted line to the transcript segment where it was said.
      segments.json: {"segments":[{"start":s,"text":"..."}]} OR a bare [ ... ] list.
      Pass "-" to read segments from stdin.
      -> JSON {"start": 372.0, "hms": "0:06:12", "score": 0.83, "text": "...",
               "deeplink": "https://www.youtube.com/watch?v=ID&t=372s"}   # deeplink iff --video-id

  link <video_id> <seconds>      -> prints https://www.youtube.com/watch?v=ID&t=Ns
  hms  <seconds>                 -> prints H:MM:SS (label for audio-only podcasts)
"""
import json
import re
import sys
from difflib import SequenceMatcher


def hms(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def yt_deeplink(video_id: str, seconds: float) -> str:
    return f"https://www.youtube.com/watch?v={video_id}&t={int(round(seconds))}s"


def _words(t: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", " ", t.lower()).split()


def match(segments: list[dict], quote: str) -> dict:
    """Return the best-matching segment window's start time for a quote."""
    qw = _words(quote)
    if not qw or not segments:
        return {"start": 0.0, "score": 0.0, "text": ""}
    qnorm = " ".join(qw)
    target = max(3, len(qw))
    best = {"start": float(segments[0].get("start", 0.0)), "score": -1.0, "text": ""}
    for i in range(len(segments)):
        window_words: list[str] = []
        text_parts: list[str] = []
        j = i
        while j < len(segments) and len(window_words) < target * 1.3 and j - i < 8:
            w = _words(segments[j].get("text", ""))
            window_words += w
            text_parts.append(segments[j].get("text", ""))
            j += 1
        if not window_words:
            continue
        cand = " ".join(window_words)
        score = SequenceMatcher(None, qnorm, cand).ratio()
        if score > best["score"]:
            best = {
                "start": float(segments[i].get("start", 0.0)),
                "score": round(score, 3),
                "text": " ".join(text_parts).strip(),
            }
    return best


def _load_segments(path: str) -> list[dict]:
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    data = json.loads(raw)
    return data["segments"] if isinstance(data, dict) else data


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "hms":
        print(hms(float(sys.argv[2])))
    elif cmd == "link":
        print(yt_deeplink(sys.argv[2], float(sys.argv[3])))
    elif cmd == "match":
        path, quote = sys.argv[2], sys.argv[3]
        video_id = None
        if "--video-id" in sys.argv:
            video_id = sys.argv[sys.argv.index("--video-id") + 1]
        res = match(_load_segments(path), quote)
        res["hms"] = hms(res["start"])
        if video_id:
            res["deeplink"] = yt_deeplink(video_id, res["start"])
        json.dump(res, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(f"unknown subcommand: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
