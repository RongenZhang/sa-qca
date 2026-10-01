#!/usr/bin/env bash
# Start SA-QCA locally: backend on :8001 and frontend on :5173, from any folder.
#   scripts/start-local.sh          start both (Ctrl+C stops both)
#   scripts/start-local.sh --check  only check prerequisites and ports
# Optional: BACKEND_PORT / FRONTEND_PORT to use other ports.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BP="${BACKEND_PORT:-8001}"; FP="${FRONTEND_PORT:-5173}"
ok=1
fail() { echo "  ✗ $1"; ok=0; }
pass() { echo "  ✓ $1"; }

echo "Checking SA-QCA prerequisites in $ROOT"
[ -x "$ROOT/backend/.venv/bin/uvicorn" ] && pass "Python environment" || fail "Python environment missing: cd backend && python3.11 -m venv .venv && .venv/bin/pip install -e \".[dev]\""
command -v Rscript >/dev/null && pass "Rscript found" || fail "Rscript not found (install R 4.5+)"
Rscript -e 'quit(status = !requireNamespace("QCA", quietly = TRUE))' >/dev/null 2>&1 && pass "R package QCA installed" || fail "R package QCA missing: Rscript -e 'install.packages(\"QCA\")'"
command -v npm >/dev/null && pass "npm found" || fail "npm not found (install Node 22+)"
[ -d "$ROOT/frontend/node_modules" ] && pass "frontend dependencies installed" || echo "  - frontend dependencies will be installed on first start"
for p in "$BP" "$FP"; do
  if lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then fail "port $p is already in use (something is already running there)"; else pass "port $p is free"; fi
done
[ "$ok" = 1 ] || { echo "Not ready."; exit 1; }
[ "${1:-}" = "--check" ] && { echo "All good."; exit 0; }

LOGS="$(mktemp -d)"
pids=()
cleanup() { echo; echo "Stopping..."; for p in "${pids[@]}"; do kill "$p" 2>/dev/null; done; wait 2>/dev/null; }
trap cleanup EXIT INT TERM

( cd "$ROOT/backend" && exec .venv/bin/uvicorn app.main:app --port "$BP" >"$LOGS/backend.log" 2>&1 ) & pids+=($!)
[ -d "$ROOT/frontend/node_modules" ] || ( cd "$ROOT/frontend" && npm install >"$LOGS/npm-install.log" 2>&1 )
( cd "$ROOT/frontend" && VITE_API_PORT="$BP" exec npm run dev -- --port "$FP" --strictPort >"$LOGS/frontend.log" 2>&1 ) & pids+=($!)

for i in $(seq 1 40); do curl -fsS "http://localhost:$BP/health" >/dev/null 2>&1 && break; sleep 0.5; done
curl -fsS "http://localhost:$BP/health" >/dev/null 2>&1 || { echo "Backend did not start; see $LOGS/backend.log"; exit 1; }
for i in $(seq 1 40); do curl -fsS "http://localhost:$FP" >/dev/null 2>&1 && break; sleep 0.5; done
echo
echo "SA-QCA is running. Open  http://localhost:$FP"
echo "Logs: $LOGS   (Ctrl+C stops everything)"
wait
