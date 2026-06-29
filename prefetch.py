#!/usr/bin/env python3
"""Stage 1 — deterministic prefetch (NO LLM, NO agent).

Does ALL the execution-heavy, injection-relevant work behind a fixed program so untrusted
content (transcripts, newsletters) can never steer a shell: discovers new items, fetches
YouTube transcripts (with timestamps), best-effort transcribes audio podcasts, fetches
newsletters via RSS/web, dedups against state. Writes:
  /tmp/brief/materials.json    -> text-only items for the reasoning stage (Stage 2)
  /tmp/brief/segments/<id>.json-> timestamped segments per A/V item (for Stage 3 matching)

Exit 0 with materials (even if empty -> "quiet day"). Run with system python3 (needs pyyaml).
"""
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import yaml

ROOT = Path("/home/abhidaas/Core/Workspace/ClaudeCode/Learning")
BRIEF = ROOT / "brief"
OUT = Path("/tmp/brief")
SEG_DIR = OUT / "segments"
VENV_PY = "/home/abhidaas/Core/Workspace/ClaudeCode/Work/gmail-mcp-env/bin/python"
WHISPER_PY = str(ROOT / ".whisper-venv/bin/python")
YT_TRANSCRIPT = str(BRIEF / "yt_transcript.py")
TRANSCRIBE = str(ROOT / "scripts/transcribe-audio.py")
UA = "Mozilla/5.0 (AI-Daily-Brief; +personal)"


def run(cmd: list[str], timeout: int = 300) -> tuple[int, str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def fetch_url(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def strip_html(html: str) -> str:
    html = html.replace("<![CDATA[", " ").replace("]]>", " ")  # unwrap CDATA (Substack feeds)
    html = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------- YouTube / podcast discovery ----------

def yt_newest(channel_url: str, n: int = 4) -> list[tuple[str, str]]:
    code, out, _ = run([
        "yt-dlp", "--flat-playlist", "--playlist-end", str(n),
        "--print", "%(id)s|%(title)s", "--", channel_url,
    ], timeout=120)
    if code != 0:
        return []
    items = []
    for line in out.splitlines():
        if "|" in line:
            vid, title = line.split("|", 1)
            items.append((vid.strip(), title.strip()))
    return items


VID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def yt_meta(video_id: str) -> dict:
    if not VID_RE.match(video_id):  # only canonical YouTube ids -> safe to interpolate
        return {}
    code, out, _ = run([
        "yt-dlp", "--skip-download",
        "--print", "%(upload_date)s|%(duration)s", "--", f"https://youtu.be/{video_id}",
    ], timeout=120)
    if code != 0 or "|" not in out:
        return {}
    d, dur = out.strip().split("|", 1)
    return {"upload_date": d.strip(), "duration": dur.strip()}


def yt_transcript(video_id: str) -> list[dict] | None:
    code, out, _ = run([VENV_PY, YT_TRANSCRIPT, video_id], timeout=180)
    if code != 0:
        return None
    try:
        return json.loads(out)["segments"]
    except Exception:
        return None


def whisper_segments(url: str) -> list[dict] | None:
    # url comes from untrusted RSS XML — reject anything that isn't a plain http(s)
    # URL (blocks argv flag-smuggling, e.g. "-x"), and pass after "--" so argparse
    # in transcribe-audio.py never treats it as an option.
    if not re.match(r"^https?://", url):
        return None
    code, out, _ = run([WHISPER_PY, TRANSCRIBE, "--json", "--", url], timeout=1800)
    if code != 0:
        return None
    try:
        return json.loads(out)["segments"]
    except Exception:
        return None


# ---------- newsletters ----------

def _feed_date(block: str) -> datetime | None:
    """Parse an item's publish date: RSS <pubDate> (RFC822) or Atom <published>/<updated> (ISO)."""
    m = (re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
         or re.search(r"<(?:published|updated)>(.*?)</(?:published|updated)>", block, re.S))
    if not m:
        return None
    raw = strip_html(m.group(1)).strip()
    dt = None
    try:
        dt = parsedate_to_datetime(raw)            # RFC822 (RSS)
    except Exception:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))  # ISO 8601 (Atom)
        except Exception:
            return None
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def newsletter_latest(nl: dict, since: datetime) -> dict | None:
    """Latest post from the newsletter's RSS/Atom feed, ONLY if newer than `since`.

    Prefers full body (<content:encoded> / Atom <content>) over the teaser <description>.
    Returns None when no working feed exists — we contribute nothing rather than scrape
    a homepage and pass nav/marketing soup downstream.
    """
    candidates = []
    if nl.get("rss"):
        candidates.append(nl["rss"])
    if nl.get("url"):
        candidates.append(nl["url"].rstrip("/") + "/feed")
        candidates.append(nl["url"].rstrip("/") + "/rss")
    for feed in candidates:
        try:
            xml = fetch_url(feed)
        except Exception:
            continue
        # first entry — feeds are reverse-chronological, so this is the newest post
        item = re.search(r"(?s)<item[ >](.*?)</item>|<entry[ >](.*?)</entry>", xml)
        if not item:
            continue
        block = item.group(1) or item.group(2) or ""
        # date gate: feed works but nothing published inside the lookback window
        pub = _feed_date(block)
        if pub is not None and pub < since:
            return None
        t = re.search(r"<title[^>]*>(.*?)</title>", block, re.S)
        link = re.search(r'<link[^>]*href="(.*?)"', block, re.S) or \
            re.search(r"<link[^>]*>(.*?)</link>", block, re.S)
        body = (re.search(r"(?s)<content:encoded>(.*?)</content:encoded>", block)
                or re.search(r"(?s)<content[^>]*>(.*?)</content>", block)
                or re.search(r"(?s)<(?:description|summary)[^>]*>(.*?)</(?:description|summary)>", block))
        text = strip_html(body.group(1))[:8000] if body else ""
        if not text:
            continue
        return {
            "title": strip_html(t.group(1)) if t else nl["name"],
            "url": strip_html(link.group(1)) if link else nl.get("url", ""),
            "text": text,
        }
    return None


# ---------- main ----------

def main() -> None:
    sources = yaml.safe_load((BRIEF / "sources.yaml").read_text())
    state = json.loads((BRIEF / "state.json").read_text())
    cfg = sources.get("config", {})
    briefed = set(state.get("briefed", []))
    lookback = timedelta(hours=cfg.get("lookback_hours", 36))
    since = datetime.now(timezone.utc) - lookback
    max_av = int(cfg.get("max_items", 8))
    max_whisper = int(cfg.get("max_whisper_per_run", 3))

    SEG_DIR.mkdir(parents=True, exist_ok=True)
    materials, whisper_used = [], 0

    # podcasts / youtube
    for pod in sources.get("podcasts", []):
        if pod.get("youtube") and len([m for m in materials if m["type"] != "newsletter"]) < max_av:
            for vid, title in yt_newest(pod["youtube"]):
                if not VID_RE.match(vid):  # guards filename + URL interpolation
                    continue
                if f"yt:{vid}" in briefed:
                    continue
                meta = yt_meta(vid)
                ud = meta.get("upload_date", "")
                if ud and len(ud) == 8:
                    when = datetime.strptime(ud, "%Y%m%d").replace(tzinfo=timezone.utc)
                    if when < since:
                        continue
                segs = yt_transcript(vid)
                if not segs:
                    continue
                (SEG_DIR / f"yt_{vid}.json").write_text(json.dumps(segs))
                materials.append({
                    "id": f"yt:{vid}", "type": "youtube", "source": pod["name"],
                    "author": pod.get("author", ""), "title": title,
                    "url": f"https://www.youtube.com/watch?v={vid}", "video_id": vid,
                    "seg_file": f"yt_{vid}.json",
                    "text": " ".join(s["text"] for s in segs)[:60000],
                })
                break  # newest qualifying ep per show
        elif pod.get("audio_only") and pod.get("rss") and whisper_used < max_whisper:
            # audio enclosure transcription is best-effort; skipped unless an mp3 url is found
            try:
                xml = fetch_url(pod["rss"])
                mp3 = re.search(r'url=\"([^\"]+\.mp3[^\"]*)\"', xml)
            except Exception:
                mp3 = None
            if mp3:
                segs = whisper_segments(mp3.group(1))
                if segs:
                    whisper_used += 1
                    key = f"audio:{abs(hash(mp3.group(1)))}"
                    if key not in briefed:
                        (SEG_DIR / f"{key.replace(':','_')}.json").write_text(json.dumps(segs))
                        materials.append({
                            "id": key, "type": "audio", "source": pod["name"],
                            "author": pod.get("author", ""), "title": pod["name"] + " (latest)",
                            "url": pod.get("url", ""), "video_id": None,
                            "seg_file": f"{key.replace(':','_')}.json",
                            "text": " ".join(s["text"] for s in segs)[:60000],
                        })

    # newsletters (web/RSS — Gmail-label sweep intentionally NOT used here; deterministic only)
    for nl in sources.get("newsletters", []):
        key = f"nl:{nl['name']}:{datetime.now(timezone.utc).date()}"
        if key in briefed:
            continue
        item = newsletter_latest(nl, since)
        if item and item.get("text"):
            materials.append({
                "id": key, "type": "newsletter", "source": nl["name"],
                "author": nl.get("author", ""), "title": item["title"],
                "url": item["url"] or nl.get("url", ""), "video_id": None,
                "seg_file": None, "text": item["text"],
            })

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "materials.json").write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(),
        "count": len(materials), "items": materials,
    }, ensure_ascii=False))
    print(f"prefetch: {len(materials)} items "
          f"({sum(1 for m in materials if m['type']=='youtube')} yt, "
          f"{sum(1 for m in materials if m['type']=='audio')} audio, "
          f"{sum(1 for m in materials if m['type']=='newsletter')} nl)", file=sys.stderr)


if __name__ == "__main__":
    main()
