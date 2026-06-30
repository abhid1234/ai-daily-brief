#!/usr/bin/env bash
# AI Daily Brief — 4-stage pipeline (secure by construction). Invoked by the systemd timer or run manually.
#
# Stage 1 prefetch.py   : deterministic. ALL yt-dlp/Whisper/feed-fetch/git happen here, NO agent — so
#                         untrusted content (transcripts, newsletters) can never steer a shell.
# Stage 2 compose       : claude -p with NO tools. Pure text in -> JSON out. An injection here can at
#                         most produce odd text; it has no shell, no network, no send capability.
# Stage 3 render.py     : deterministic. Matches quotes->timestamps, renders the one-pager, archives, commits.
# Stage 4 deliver       : claude -p with SEND-ONLY tools (gmail_send + telegram + Read). NO Bash.
#
# The yt-dlp --exec hole is gone: the agent never invokes yt-dlp. Logs -> brief/logs/.
set -uo pipefail
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

# Self-locate: BRIEF is the dir this script lives in, so the pipeline runs from anywhere.
BRIEF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="${BRIEF_TMP:-/tmp/brief}"
TODAY="$(date +%Y-%m-%d)"
LOG_DIR="$BRIEF/logs"; mkdir -p "$LOG_DIR" "$TMP"
LOG="$LOG_DIR/$TODAY.log"

main() {
  echo "=== ai-brief $TODAY start $(date -Is) ==="
  cd "$BRIEF" || exit 1

  # Stage 0 — idempotency
  if [ "$(python3 -c "import json;print(json.load(open('$BRIEF/state.json')).get('lastRun'))")" = "$TODAY" ] \
     && [ "${1:-}" != "force" ]; then
    echo "already ran today — exiting"; return 0
  fi

  # Stage 1 — deterministic prefetch
  echo "--- stage 1: prefetch ---"
  if ! python3 "$BRIEF/prefetch.py"; then echo "prefetch failed"; return 1; fi
  COUNT="$(python3 -c "import json;print(json.load(open('$TMP/materials.json'))['count'])")"
  echo "materials: $COUNT items"
  if [ "$COUNT" = "0" ]; then
    echo "quiet day — nothing new; marking run and exiting (no email)."
    python3 -c "import json,datetime;p='$BRIEF/state.json';s=json.load(open(p));s['lastRun']='$TODAY';json.dump(s,open(p,'w'),indent=2)"
    git add -A >/dev/null 2>&1; git commit -m "brief: $TODAY (quiet day)" >/dev/null 2>&1
    return 0
  fi

  # Stage 2 — reasoning (NO tools). Build prompt = instructions + materials, feed via stdin.
  echo "--- stage 2: compose (no tools) ---"
  { sed "s/<TODAY>/$TODAY/g" "$BRIEF/prompts/compose.md"; echo; echo "MATERIALS:"; cat "$TMP/materials.json"; } > "$TMP/compose_input.txt"
  claude -p --permission-mode default --allowedTools "" < "$TMP/compose_input.txt" > "$TMP/stage2_out.txt" 2>>"$LOG" || { echo "compose failed"; return 1; }
  if ! python3 "$BRIEF/extract_json.py" < "$TMP/stage2_out.txt"; then echo "no valid draft JSON — aborting (no broken brief sent)"; return 1; fi

  # Stage 3 — deterministic render + persist + commit
  echo "--- stage 3: render ---"
  if ! python3 "$BRIEF/render.py" "$TMP/draft.json"; then echo "render failed"; return 1; fi

  # Stage 3.5 — audio (deterministic, best-effort, opt-in via delivery.audio)
  AUDIO="$(python3 -c "import yaml;print(yaml.safe_load(open('$BRIEF/sources.yaml')).get('delivery',{}).get('audio',False))" 2>/dev/null)"
  if [ "$AUDIO" = "True" ]; then
    echo "--- stage 3.5: tts ---"
    python3 "$BRIEF/tts.py" || echo "tts reported non-zero (audio skipped)"
  fi

  # Stage 4 — delivery (send-only tools, NO Bash)
  echo "--- stage 4: deliver ---"
  claude -p "$(sed "s#<BRIEF_DIR>#$BRIEF#g" "$BRIEF/prompts/deliver.md")" \
    --permission-mode default \
    --allowedTools "Read,mcp__google-workspace__gmail_send,mcp__plugin_telegram_telegram__reply" \
    >>"$LOG" 2>&1 || echo "deliver reported non-zero (check log)"

  echo "=== ai-brief $TODAY end $(date -Is) ==="
}

main "${1:-}" >>"$LOG" 2>&1
