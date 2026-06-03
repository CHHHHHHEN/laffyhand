#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
UI_DIR="$PROJECT_DIR/laffyhand/ui"

echo "=== Stopping existing laffyhand process ==="
pkill -f "laffyhand" 2>/dev/null || echo "(none running)"
sleep 1

echo ""
echo "=== Building UI ==="
cd "$UI_DIR"
pnpm build

echo ""
echo "=== Starting laffyhand backend ==="
cd "$PROJECT_DIR"
exec uv run laffyhand ui --host 127.0.0.1 --port 9090
