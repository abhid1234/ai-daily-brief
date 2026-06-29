#!/usr/bin/env python3
"""Fetch a YouTube transcript WITH per-segment timestamps (for minute-accurate deep links).

Run with the interpreter that has youtube-transcript-api installed:
    ~/Core/Workspace/ClaudeCode/Work/gmail-mcp-env/bin/python yt_transcript.py <url-or-id>

Output (stdout, JSON):
    {"video_id": "...", "segments": [{"start": 12.3, "duration": 4.1, "text": "..."}]}
Exit codes: 0 ok, 1 bad input, 2 no transcript available.
"""
import json
import re
import sys


def video_id(s: str) -> str:
    """Accept a raw id or any common YouTube URL form."""
    s = s.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    m = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    raise ValueError(f"could not extract a video id from: {s}")


def fetch(vid: str) -> list[dict]:
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    fetched = api.fetch(vid)  # new-API instance method -> FetchedTranscript
    out = []
    for snip in fetched:  # FetchedTranscript is iterable over snippets
        out.append({
            "start": round(float(snip.start), 2),
            "duration": round(float(getattr(snip, "duration", 0.0)), 2),
            "text": snip.text.strip(),
        })
    return out


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: yt_transcript.py <url-or-id>", file=sys.stderr)
        sys.exit(1)
    try:
        vid = video_id(sys.argv[1])
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    try:
        segments = fetch(vid)
    except Exception as e:
        print(f"no transcript for {vid}: {e}", file=sys.stderr)
        sys.exit(2)
    json.dump({"video_id": vid, "segments": segments}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
