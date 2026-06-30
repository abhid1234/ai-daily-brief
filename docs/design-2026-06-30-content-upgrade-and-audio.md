# Design — Content upgrade + Audio edition (2026-06-30)

Two sub-projects to turn the brief from an *aggregator* into *intelligence*. Weekly digest is a
separate future sub-project (deferred).

## A. Daily content upgrade

Four new elements in the Frontier Notes layout, all driven by the reasoning stage (`compose.md`)
and rendered deterministically (`render.py`). Every new string flows through `rich()`/`escape()`.

### A1. Developing Story (cross-day theme tracker)
- `state.json` gains `themes: [{slug, label, dates: ["YYYY-MM-DD", ...]}]`, pruned to the last 14 days.
- `prefetch.py` reads recent themes and writes `recent_themes` into `materials.json` (slug + label +
  days_active + last_seen) so the tool-less compose stage has cross-day context.
- `compose.md` outputs `developing: [{slug, label, status: "new"|"continuing"}]`, reusing an existing
  slug when today's story continues one.
- `render.py` is the source of truth for the **day count**: it matches each developing slug against
  `state.themes`, appends today's date, computes `days_running` = count of distinct dates, renders a
  compact strip ("📈 Day 3 — Agent security · New — Open-weights race"), then persists/prunes themes.
  The LLM never supplies the number.

### A2. By the Numbers
- `compose.md` outputs `by_the_numbers: [{figure, label}]`. Anti-hallucination rule: include a figure
  ONLY if it appears verbatim in a source item's text.
- `render.py` shows a stat strip near the top (after the editor take).

### A3. The Debate
- `compose.md` outputs `debate: {question, side_a:{who,view}, side_b:{who,view}}` or null when there's
  no genuine disagreement that day.
- `render.py` shows a callout box (only when present).

### A4. Glossary
- `compose.md` outputs `glossary: [{term, definition}]` — jargon a business operator wouldn't know.
- `render.py` renders a small aside before the footer.

## B. Audio edition

- `compose.md` outputs `audio_script`: a conversational 2–4 min spoken version (no markdown). Written
  to `/tmp/brief/audio_script.txt` by `render.py`.
- New deterministic stage `tts.py` (between render and deliver): reads the script, calls **Google Cloud
  Text-to-Speech REST** with an ADC token (`gcloud auth application-default print-access-token`),
  stdlib `urllib` only (no pip — corp airlock safe), voice `en-US-Journey-D`, writes `/tmp/brief/brief.mp3`.
  Best-effort: skips gracefully if ADC/scope missing. Gated by `sources.yaml → delivery.audio: true`.
- `deliver.md` attaches `brief.mp3` to Telegram (file) and to the email (if the send tool supports
  attachments — to verify; else Telegram-only with a logged note).

## Sequencing
A then B this round. Security model unchanged (injection-exposed stages have no execution;
deterministic stages do all I/O). Weekly digest = future sub-project (reuses theme state + archive).
