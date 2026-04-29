#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="codex-upstream-sync.service"
TIMER_NAME="codex-upstream-sync.timer"
SERVICE_PATH="$USER_SYSTEMD_DIR/$SERVICE_NAME"
TIMER_PATH="$USER_SYSTEMD_DIR/$TIMER_NAME"

mkdir -p "$USER_SYSTEMD_DIR"

# Build PATH that includes node if available (e.g. from nvm)
NODE_BIN_DIR=""
if command -v node >/dev/null 2>&1; then
  NODE_BIN_DIR="$(dirname "$(command -v node)")"
fi
ENV_PATH="PATH=${NODE_BIN_DIR:+$NODE_BIN_DIR:}/usr/local/bin:/usr/bin:/bin"

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Sync managed upstream skill repositories for Codex

[Service]
Type=oneshot
WorkingDirectory=$PROJECT_ROOT
Environment="$ENV_PATH"
Environment="SKILL_AGENT_TARGETS=all"
ExecStart=/usr/bin/env python3 $ROOT_DIR/scripts/sync_all_upstreams.py --manifest $ROOT_DIR/migration/upstream-manifest.yaml --relink
EOF

cat > "$TIMER_PATH" <<EOF
[Unit]
Description=Weekly sync of managed upstream skill repositories for Codex

[Timer]
OnCalendar=weekly
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "$TIMER_NAME"

echo "Installed $SERVICE_NAME and $TIMER_NAME"
