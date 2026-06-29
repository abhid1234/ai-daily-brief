#!/usr/bin/env bash
# Install the AI Daily Brief systemd user timer (runs 07:30 daily, laptop-closed-safe via linger).
# Idempotent. Run: bash ~/Core/Workspace/ClaudeCode/Learning/brief/systemd/install.sh
set -euo pipefail

SRC="$HOME/Core/Workspace/ClaudeCode/Learning/brief/systemd"
DEST="$HOME/.config/systemd/user"
mkdir -p "$DEST"
chmod +x "$HOME/Core/Workspace/ClaudeCode/Learning/brief/run-brief.sh"
cp "$SRC/ai-brief.service" "$SRC/ai-brief.timer" "$DEST/"

systemctl --user daemon-reload
systemctl --user enable --now ai-brief.timer
# Linger lets the timer fire even when you're not logged in interactively.
loginctl enable-linger "$USER" 2>/dev/null || true

echo "Installed. Next runs:"
systemctl --user list-timers ai-brief.timer --no-pager
echo
echo "Manual test any time:  systemctl --user start ai-brief.service  (then tail brief/logs/<today>.log)"
echo "Disable:               systemctl --user disable --now ai-brief.timer"
