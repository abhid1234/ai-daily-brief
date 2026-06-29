#!/usr/bin/env python3
"""Stage 3 — deterministic render + persist (NO LLM, NO agent).

Reads the reasoning stage's draft (/tmp/brief/draft.json), resolves each A/V quote to the exact
second via the saved segments (link.match), renders the one-pager (markdown + email HTML), archives
it to the wiki, updates state.json, and commits. Outputs for Stage 4 (delivery):
  /tmp/brief/brief.md  /tmp/brief/brief.html  /tmp/brief/subject.txt
Run with system python3 (imports link.py from this dir).
"""
import json
import re
import subprocess
import sys
from datetime import date, datetime
from html import escape
from pathlib import Path
from urllib.parse import urlparse

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import link  # noqa: E402  (local, stdlib-only)

ROOT = Path("/home/abhidaas/Core/Workspace/ClaudeCode/Learning")
BRIEF = ROOT / "brief"
OUT = Path("/tmp/brief")
SEG_DIR = OUT / "segments"
WIKI_BRIEFS = ROOT / "wiki/briefs"


def resolve_link(item: dict, min_score: float) -> tuple[str, str]:
    """Return (href, label) for an item. Minute-accurate for youtube, label-only for audio."""
    if item["type"] == "newsletter" or not item.get("quote") or not item.get("seg_file"):
        return item.get("url", ""), ""
    seg_path = SEG_DIR / item["seg_file"]
    if not seg_path.exists():
        return item.get("url", ""), ""
    segs = json.loads(seg_path.read_text())
    m = link.match(segs, item["quote"])
    start = m["start"]
    if item["type"] == "youtube" and m["score"] >= min_score and item.get("video_id"):
        return link.yt_deeplink(item["video_id"], start), f"▶ {link.hms(start)}"
    if item["type"] == "audio":
        return item.get("url", ""), f"[{link.hms(start)}]"
    return item.get("url", ""), f"{link.hms(start)} (approx)"


OX = "#7c2128"  # oxblood accent

# Preferred section order; any LLM-named section not listed renders after these, first-seen order.
SECTION_ORDER = [
    "The Lead", "Research & Models", "Models & Releases", "Research", "Agents & Tooling",
    "Policy & Safety", "Governance & Safety", "Safety & Security", "Business & Markets",
    "Funding & Business", "Infrastructure & Compute", "Science & Robotics", "Industry",
]


def fmt_date(d: str) -> str:
    """2026-06-23 -> 'Tuesday, June 23, 2026' (falls back to raw on parse failure)."""
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
        return f'{dt.strftime("%A, %B")} {dt.day}, {dt.year}'
    except Exception:
        return d


def rich(text: str) -> str:
    """Escape untrusted text, THEN allow only **bold**/*italic* -> <b>/<i>.

    Escaping happens first, so the captured spans are already inert; the only tags this can
    emit are <b>/<i>, never attacker-controlled markup. Safe for LLM-derived strings.
    """
    t = escape((text or "").strip())
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", t)
    return t


def _clean_ts(label: str) -> str:
    """'▶ 0:12:29' / '[0:12:29]' -> '12:29' (drop a leading zero-hour for readability)."""
    ts = label.lstrip("▶[] ").rstrip("] ").strip()
    return ts[2:] if ts.startswith("0:") else ts


def cta_for(item: dict, label: str, has_href: bool) -> str:
    """Action label. Video -> 'Watch at MM:SS', audio -> 'Listen at MM:SS', else read."""
    typ = item.get("type")
    if typ == "youtube" and label:
        return f"▶ Watch at {_clean_ts(label)}  →"
    if typ == "audio" and label:
        return f"🎧 Listen at {_clean_ts(label)}  →"
    if typ == "youtube":
        return "▶ Watch the episode  →"
    if typ == "audio":
        return "🎧 Listen to the episode  →"
    if has_href:
        return "Read the issue  →"
    return ""


def section_header(title: str, count) -> str:
    cnt = ""
    if count:
        unit = "item" if count == 1 else "items"
        cnt = (f' &nbsp;<span style="color:#b3a994;font-style:italic;letter-spacing:0;'
               f'text-transform:none;font-weight:400">· {count} {unit}</span>')
    return (
        f'<div style="font:600 13px/1 Georgia,serif;letter-spacing:.2em;text-transform:uppercase;'
        f'color:{OX};margin:28px 0 0">' + escape(title) + cnt + '</div>'
        '<hr style="border:0;border-top:1px solid #ddd3c2;margin:8px 0 4px">'
    )


def cite_html(item: dict, min_score: float) -> str:
    """Attribution line (muted) + a prominent action link.

    Podcasts resolve to a minute-accurate deep-link rendered as an oxblood chip
    (▶ Watch at 12:29 for video — jumps to the exact second; 🎧 Listen at 41:05 for
    audio). Newsletters get an underlined 'Read the issue' link.
    """
    href, label = resolve_link(item, min_score)
    typ = item.get("type")
    icon = "▶" if typ in ("youtube", "audio") else "✉"
    type_label = "Podcast" if typ in ("youtube", "audio") else "Newsletter"
    safe_href = href if urlparse(href).scheme in ("http", "https", "mailto") else ""
    cta = cta_for(item, label, bool(safe_href))
    timestamped = typ in ("youtube", "audio") and bool(label)  # a real matched moment

    # attribution (small-caps, muted): icon · source · author/type
    parts = [escape((item.get("source") or "").strip())]
    parts.append(escape((item.get("author") or "").strip()) or type_label)
    src = " · ".join(p for p in parts if p)
    attribution = ('<div style="font:600 11.5px/1.5 Georgia,serif;letter-spacing:.1em;'
                   f'text-transform:uppercase;color:#9a917f;margin:0 0 2px">'
                   f'<span style="color:{OX}">{icon}</span> ' + src + '</div>')

    if not (safe_href and cta):
        return attribution
    href_attr = escape(safe_href, quote=True)
    if timestamped:
        # prominent oxblood chip — the "jump to the exact moment" link the reader scans for
        action = (f'<a href="{href_attr}" style="display:inline-block;margin:6px 0 2px;'
                  f'padding:6px 13px;border:1px solid {OX};border-radius:4px;color:{OX};'
                  f'font:600 12.5px/1 Georgia,serif;letter-spacing:.03em;text-decoration:none">'
                  + escape(cta) + '</a>')
    else:
        action = (f'<a href="{href_attr}" style="display:inline-block;margin:4px 0 2px;'
                  f'color:{OX};text-decoration:none;border-bottom:1px solid #e0c5c7;'
                  f'font-size:13.5px">' + escape(cta) + '</a>')
    return attribution + action


def item_html(item: dict, min_score: float) -> str:
    """One story: bold lead-in headline -> explanation -> nested evidence -> cited source."""
    details = item.get("details") or []
    ev = ""
    lis = "".join(
        '<li style="font-size:14.5px;line-height:1.55;color:#544c40;margin:0 0 3px">'
        + (f'<b style="color:#3a342b">{rich(d.get("label", ""))}:</b> ' if d.get("label") else "")
        + rich(d.get("text", "")) + '</li>'
        for d in details if isinstance(d, dict) and (d.get("text") or d.get("label")))
    if lis:
        ev = f'<ul style="margin:4px 0 8px;padding-left:20px">{lis}</ul>'
    return (
        '<div style="padding:12px 0 2px">'
        f'<div style="font-size:17px;line-height:1.5;color:#23201c;margin:0 0 5px">'
        f'<b>{escape((item.get("headline") or "").strip())}</b></div>'
        '<div style="font-size:15.5px;line-height:1.62;color:#403a30;margin:0 0 7px">'
        + rich(item.get("why") or "") + '</div>' + ev + cite_html(item, min_score) + '</div>'
    )


def render(draft: dict, min_score: float, stats: dict | None = None) -> tuple[str, str]:
    """Render the 'Frontier Notes' editorial issue (AINews-style sections) — markdown + email HTML.

    SECURITY: every LLM-derived string (editor_take, headline, why, details, quote_of_day,
    quick_hits, what_to_watch, footer) is escape()'d via rich()/escape() before entering HTML,
    and only http(s)/mailto hrefs are emitted — an injected <script>/onerror or javascript:/data:
    URI cannot render. rich() can only ever add <b>/<i>.
    """
    d = draft.get("date") or str(date.today())
    take = (draft.get("editor_take") or draft.get("summary") or "").strip()
    qod = draft.get("quote_of_day") or {}
    watch = (draft.get("what_to_watch") or "").strip()
    footer = draft.get("footer", "")
    dateline = (draft.get("dateline") or "").strip()
    items = draft.get("items", [])
    quick = draft.get("quick_hits", []) or []

    # group items by section, preserving LLM order within a section
    groups: dict[str, list] = {}
    seen_order: list[str] = []
    for it in items:
        sec = (it.get("section") or "Today").strip() or "Today"
        if sec not in groups:
            groups[sec] = []
            seen_order.append(sec)
        groups[sec].append(it)
    ordered = ([s for s in SECTION_ORDER if s in groups]
               + [s for s in seen_order if s not in SECTION_ORDER])

    # ---------------- markdown (wiki archive) ----------------
    md = [f"# 🧠 AI Daily Brief — {d}", ""]
    if take:
        md += [take, ""]
    if qod.get("text"):
        md += [f"> {qod['text']}", f"> — {qod.get('attribution', '')}".rstrip(" —"), ""]
    n = 0
    for sec in ordered:
        md += [f"## {sec}", ""]
        for it in groups[sec]:
            n += 1
            href, label = resolve_link(it, min_score)
            safe = href if urlparse(href).scheme in ("http", "https", "mailto") else ""
            cta = cta_for(it, label, bool(safe))
            src_md = " · ".join(x for x in [it.get("source"), it.get("author")] if x)
            md += [f"**{it.get('headline', '')}**  ", f"{it.get('why', '')}  "]
            for dt in (it.get("details") or []):
                if isinstance(dt, dict) and (dt.get("text") or dt.get("label")):
                    lbl = f"**{dt['label']}:** " if dt.get("label") else ""
                    md += [f"- {lbl}{dt.get('text', '')}"]
            md += [f"*{src_md}* — [{cta or 'source'}]({href})" if safe else f"*{src_md}*", ""]
    if quick:
        md += ["## Also Notable", ""]
        for q in quick:
            href = q.get("url", "")
            safe = href if urlparse(href).scheme in ("http", "https") else ""
            lead = f"**{q['source']}:** " if q.get("source") else ""
            tail = f" [{('Listen' if q.get('type') in ('youtube', 'audio') else 'Read')} →]({href})" if safe else ""
            md += [f"- {lead}{q.get('text', '')}{tail}"]
        md += [""]
    if watch:
        md += ["## What to Watch", "", watch, ""]
    if footer:
        md += ["---", f"_{footer}_"]

    # ---------------- html (email) ----------------
    head = (
        '<div style="text-align:center;padding:6px 0 0">'
        f'<div style="font:600 12px/1 Georgia,serif;letter-spacing:.32em;text-transform:uppercase;color:{OX}">The AI Daily Brief</div>'
        '<div style="font-size:40px;font-weight:700;color:#23201c;margin:10px 0 4px">Frontier Notes</div>'
        f'<div style="font-style:italic;color:#6b645a;font-size:15px">{escape(fmt_date(str(d)))}</div></div>'
        f'<hr style="border:0;border-top:3px double {OX};margin:18px 0 0">'
    )

    stats_html = ""
    if stats:
        dl = escape(dateline or fmt_date(str(d)))
        txt = (f'AI news for <b>{dl}</b>. We scanned <b>{stats.get("podcasts", 0)} podcasts</b> '
               f'and <b>{stats.get("newsletters", 0)} newsletters</b>')
        if stats.get("items_seen"):
            txt += f' — <b>{stats["items_seen"]} new items</b>, {stats.get("selected", n)} worth your time'
        txt += "."
        if stats.get("read_min"):
            txt += f' Reading time saved (at 200wpm): <b>~{stats["read_min"]} minutes</b>.'
        stats_html = ('<div style="font-size:13.5px;line-height:1.6;color:#8a8275;font-style:italic;'
                      f'padding:20px 0 0">{txt}</div>')

    take_html = ('<div style="font-size:16.5px;line-height:1.66;color:#2c2822;padding:14px 0 0">'
                 + rich(take) + '</div>') if take else ""

    qod_html = ""
    if qod.get("text"):
        attr = (f'<span style="display:block;font-size:13px;font-style:normal;color:#8a8275;'
                f'letter-spacing:.04em;margin-top:6px">{escape(qod.get("attribution", ""))}</span>'
                ) if qod.get("attribution") else ""
        qod_html = (f'<div style="border-left:3px solid {OX};margin:20px 0 2px;padding:4px 0 4px 18px;'
                    f'font-size:18px;font-style:italic;color:#4a443b;line-height:1.5">'
                    + escape(qod["text"]) + attr + '</div>')

    secs = []
    for sec in ordered:
        its = groups[sec]
        secs.append(section_header(sec, None if sec == "The Lead" else len(its)))
        secs += [item_html(it, min_score) for it in its]

    qh_html = ""
    if quick:
        lis = []
        for q in quick:
            href = q.get("url", "")
            safe = href if urlparse(href).scheme in ("http", "https") else ""
            verb = "Listen" if q.get("type") in ("youtube", "audio") else "Read"
            link = (f' <a href="{escape(safe, quote=True)}" style="color:{OX};text-decoration:none;'
                    f'border-bottom:1px solid #e0c5c7">{verb} →</a>') if safe else ""
            lead = f'<b style="color:#23201c">{escape(q["source"].strip())}:</b> ' if q.get("source") else ""
            lis.append('<li style="font-size:14.5px;line-height:1.6;color:#403a30;margin:0 0 6px">'
                       + lead + rich(q.get("text", "")) + link + '</li>')
        qh_html = (section_header("Also Notable", None)
                   + f'<ul style="margin:6px 0 0;padding-left:20px">{"".join(lis)}</ul>')

    watch_html = ""
    if watch:
        watch_html = ('<div style="background:#f2ecdf;border:1px solid #e6ddc9;border-radius:6px;'
                      'padding:14px 18px;margin:24px 0 0;font-size:14.5px;line-height:1.6;color:#4a4334">'
                      f'<div style="color:{OX};letter-spacing:.14em;text-transform:uppercase;font-size:12px;'
                      'font-weight:700;margin-bottom:6px">What to Watch</div>' + rich(watch) + '</div>')

    foot_html = (
        '<hr style="border:0;border-top:1px solid #e2dacb;margin:24px 0 0">'
        '<div style="font-size:12.5px;line-height:1.55;color:#9b9384;font-style:italic;padding:16px 0 0">'
        + escape(footer) + '</div>') if footer else ""

    html = (
        '<div style="background:#ece6da;padding:24px 0;margin:0">'
        '<div style="max-width:660px;margin:0 auto;background:#faf7f1;padding:34px 46px 38px;'
        "font-family:Georgia,'Times New Roman',serif;color:#23201c\">"
        + head + stats_html + take_html + qod_html + "".join(secs)
        + qh_html + watch_html + foot_html + '</div></div>'
    )
    return "\n".join(md), html


def main() -> None:
    draft = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else OUT / "draft.json").read_text())
    sources = yaml.safe_load((BRIEF / "sources.yaml").read_text())
    min_score = float(sources.get("config", {}).get("min_match_score", 0.55))

    # deterministic stats (never LLM-supplied numbers): source counts from config, items + reading
    # time from the prefetch materials the reasoning stage actually saw.
    mat = {}
    mat_path = OUT / "materials.json"
    if mat_path.exists():
        try:
            mat = json.loads(mat_path.read_text())
        except Exception:
            mat = {}
    mat_items = mat.get("items", [])
    words = sum(len((m.get("text") or "").split()) for m in mat_items)
    stats = {
        "podcasts": len(sources.get("podcasts", [])),
        "newsletters": len(sources.get("newsletters", [])),
        "items_seen": mat.get("count") or len(mat_items),
        "selected": len(draft.get("items", [])) + len(draft.get("quick_hits", []) or []),
        "read_min": (max(1, round(words / 200)) if words else None),
    }

    md, html = render(draft, min_score, stats)
    today = str(date.today())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "brief.md").write_text(md)
    (OUT / "brief.html").write_text(html)
    (OUT / "subject.txt").write_text(f"🧠 AI Daily Brief — {today}")

    # archive to wiki
    WIKI_BRIEFS.mkdir(parents=True, exist_ok=True)
    (WIKI_BRIEFS / f"{today}.md").write_text(md)
    log = ROOT / "wiki/log.md"
    if log.exists():
        with log.open("a") as f:
            f.write(f"\n- {today} BRIEF -> wiki/briefs/{today}.md ({len(draft.get('items', []))} items)")

    # update state (dedup + lastRun)
    state = json.loads((BRIEF / "state.json").read_text())
    ids = {it["id"] for it in draft.get("items", [])}
    state["briefed"] = sorted(set(state.get("briefed", [])) | ids)[-2000:]
    state["lastRun"] = today
    (BRIEF / "state.json").write_text(json.dumps(state, indent=2) + "\n")

    # commit (no push)
    subprocess.run(["git", "add", "-A"], cwd=ROOT, capture_output=True)
    subprocess.run(["git", "commit", "-m", f"brief: {today} ({len(ids)} items)"],
                   cwd=ROOT, capture_output=True)
    print(str(WIKI_BRIEFS / f"{today}.md"))


if __name__ == "__main__":
    main()
