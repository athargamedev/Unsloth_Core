#!/usr/bin/env bash
# ── Confident AI Tunnel: Start dashboard + ngrok ─────────────────────────────
# Starts the dashboard dev server on port 3100 and an ngrok tunnel to it.
# Prints the ngrok URL for configuration in Confident AI AI Connection settings.
#
# Usage:
#   ./scripts/confident-tunnel.sh          # start both
#   ./scripts/confident-tunnel.sh stop     # stop both
#   ./scripts/confident-tunnel.sh url      # show current ngrok URL
#
# Requires: ngrok installed, npm deps installed in src/dashboard/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DASHBOARD_DIR="$PROJECT_ROOT/src/dashboard/unity-npc-llm-training-dashboard"
DASHBOARD_PORT="${PORT:-3100}"
NGROK_DOMAIN="${NGROK_DOMAIN:-}"  # set to a reserved domain if you have a paid plan

PID_FILE="$PROJECT_ROOT/var/.pipeline/confident-tunnel.pid"
NGROK_PID_FILE="$PROJECT_ROOT/var/.pipeline/ngrok.pid"

mkdir -p "$(dirname "$PID_FILE")"

stop_tunnel() {
  echo "Stopping dashboard + ngrok..."
  if [ -f "$PID_FILE" ]; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    rm -f "$PID_FILE"
  fi
  if [ -f "$NGROK_PID_FILE" ]; then
    kill "$(cat "$NGROK_PID_FILE")" 2>/dev/null || true
    rm -f "$NGROK_PID_FILE"
  fi
  # Kill any remaining ngrok processes from this session
  pkill -f "ngrok http $DASHBOARD_PORT" 2>/dev/null || true
  echo "Stopped."
}

show_url() {
  # Fetch the ngrok API for tunnel info
  local url
  url=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for t in data.get('tunnels', []):
        if t.get('public_url', '').startswith('https://'):
            print(t['public_url'])
            break
except Exception:
    pass
" 2>/dev/null)
  if [ -n "$url" ]; then
    echo "Ngrok URL: $url"
    echo ""
    echo "In Confident AI, configure the AI Connection with:"
    echo "  Endpoint URL: $url/api/confident/generate"
    echo "  Health Check:  $url/api/confident/health"
    echo "  Models List:   $url/api/confident/models"
    echo ""
    echo "Test it:"
    echo "  curl -X POST $url/api/confident/generate \\"
    echo '    -H "Content-Type: application/json" \'
    echo '    -d '\''{"input":"Tell me about yourself","hyperparameters":{"npc_key":"chef_assistant"}}'\'''
    echo ""
    echo "Note: The endpoint uses llama.cpp (port 18080) — ensure ~/llama-servers.sh is running."
    return 0
  else
    echo "Ngrok does not seem to be running (no tunnel at 127.0.0.1:4040)."
    echo "Start with: $0"
    return 1
  fi
}

case "${1:-}" in
  stop)
    stop_tunnel
    exit 0
    ;;
  url)
    show_url
    exit $?
    ;;
  restart)
    stop_tunnel
    exec "$0"
    ;;
esac

# ── Prerequisites ────────────────────────────────────────────────────────────

if ! command -v ngrok &>/dev/null; then
  echo "ERROR: ngrok not found. Install from https://ngrok.com/download"
  exit 1
fi

if [ ! -d "$DASHBOARD_DIR/node_modules" ]; then
  echo "Installing dashboard dependencies..."
  (cd "$DASHBOARD_DIR" && npm install)
fi

# ── Cleanup on exit ──────────────────────────────────────────────────────────

cleanup() {
  stop_tunnel
}
trap cleanup EXIT INT TERM

# ── Start ngrok ──────────────────────────────────────────────────────────────

echo "Starting ngrok tunnel → http://localhost:$DASHBOARD_PORT ..."
NGROK_ARGS="http $DASHBOARD_PORT --log=stdout"
if [ -n "$NGROK_DOMAIN" ]; then
  NGROK_ARGS="$NGROK_ARGS --domain=$NGROK_DOMAIN"
fi
ngrok $NGROK_ARGS &
NGROK_PID=$!
echo "$NGROK_PID" > "$NGROK_PID_FILE"

# Wait for ngrok to be ready
for i in $(seq 1 15); do
  if curl -s http://127.0.0.1:4040/api/tunnels >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# ── Show ngrok URL ───────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           Confident AI Tunnel — ACTIVE                       ║"
show_url
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Start dashboard ──────────────────────────────────────────────────────────

echo "Starting dashboard on port $DASHBOARD_PORT ..."
cd "$DASHBOARD_DIR"
exec npx tsx watch server.ts
