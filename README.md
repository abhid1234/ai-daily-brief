# AI Daily Brief

A daily one-pager of ONLY top AI newsletters + top-rated podcasts, with **minute-accurate** source
links (for video/podcast insights, a link to the exact second the line was said). Triple-delivered:
auto-email to both inboxes + Telegram push + wiki archive.

## Secure 4-stage pipeline (`run-brief.sh`)
Built so untrusted content (podcast captions, newsletter HTML) can **never reach an agent that holds a
shell** — the injection-exposed stages have no execution:

| Stage | What | Capability |
|-------|------|-----------|
| 1 `prefetch.py` | discover + fetch: yt-dlp, YouTube transcripts (timestamps), best-effort audio Whisper, newsletter RSS/web | **deterministic, no agent** |
| 2 compose (`claude -p`) | rank to top 5–8, pick verbatim quotes → draft JSON | **no tools at all** |
| 3 `render.py` | match quotes→exact second, render brief, archive to wiki, update state, commit | **deterministic, no agent** |
| 4 deliver (`claude -p`) | send the rendered brief | **send-only: gmail_send + telegram + Read, no Bash** |

`extract_json.py` salvages the Stage-2 JSON (tolerates fences/prose). The `yt-dlp --exec` risk is gone:
the agent never invokes yt-dlp.

## Run
```bash
bash ~/Core/Workspace/ClaudeCode/Learning/brief/run-brief.sh          # full pipeline (idempotent)
bash ~/Core/Workspace/ClaudeCode/Learning/brief/run-brief.sh force    # re-run a day
```
Or `/ai-brief` in Claude Code (thin launcher for the same script). Daily automation: `systemd/install.sh`
(07:30 timer, catch-up via `Persistent=true`, no `bypassPermissions`).

## Files
| File | Role |
|------|------|
| `sources.yaml` | source list + delivery (both emails) + config. **Edit anytime.** |
| `state.json` | dedup ledger + `lastRun` (idempotency); committed so the cloud net sees local runs |
| `prefetch.py` / `render.py` | the two deterministic stages (no LLM) |
| `prompts/compose.md` · `prompts/deliver.md` | the two minimal-capability agent stages |
| `yt_transcript.py` | YouTube transcript with timestamps (gmail-mcp-env python) |
| `link.py` | `match` (quote→second), `link` (deeplink), `hms` (audio label) — pure stdlib |
| `../scripts/transcribe-audio.py` | Whisper; `--json` emits timestamped segments |
| `cloud-brief-prompt.md` | laptop-closed `/schedule` safety net (GitHub issue) |
| `systemd/` | user timer + installer |

## Honest limits
- Clickable minute-jumps work for **YouTube** only. Audio-only podcasts get `[H:MM:SS]` labels (no deep-link standard exists); add an `rss:` field to a podcast to enable best-effort Whisper.
- Newsletters come from **RSS/web** (not the Gmail label) so Stage 1 stays a no-agent program. Add `rss:` per newsletter for reliability.
- Shows with no episode inside `lookback_hours` are skipped (correct). If a `youtube:` handle is wrong, fix it in `sources.yaml`.
- Whisper is slow on CPU → capped at `max_whisper_per_run`.

## Note on paths (standalone mirror)

This is a standalone mirror of the tool, extracted from a larger monorepo. The Python/shell entry
points still contain **absolute paths to the original author's machine** (e.g. `ROOT = /home/.../Learning`,
a venv path in `prefetch.py`, and `scripts/transcribe-audio.py`). To run it elsewhere, update those
constants at the top of `prefetch.py`, `render.py`, and `run-brief.sh`. The audio-transcription helper
is bundled under `scripts/`. Requires: `python3` + `pyyaml`, `yt-dlp`, and (for audio) a Whisper venv;
delivery uses the Claude Code CLI with send-only tools.
