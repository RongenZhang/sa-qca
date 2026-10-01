#!/usr/bin/env bash
# Smoke test for a running SA-QCA demo:  deploy/smoke.sh http://localhost:7860
set -euo pipefail
BASE="${1:-http://localhost:7860}"
SID="smoke$(date +%s)smoketest"
H=(-H "X-Session: $SID" -H "Content-Type: application/json")

echo "health";    curl -fsS "$BASE/health" | grep -q '"ok"'
echo "frontend";  curl -fsS "$BASE/" | grep -qi "Stakeholder Anchors"
echo "mode";      curl -fsS "$BASE/api/mode" | grep -q '"demo"'
echo "upload blocked"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -F "file=@/dev/null;filename=a.csv" -H "X-Session: $SID" "$BASE/api/projects/upload")
[ "$code" = "403" ] || { echo "expected 403, got $code"; exit 1; }
echo "real provider refused"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${H[@]}" -d '{"provider":"anthropic","model":"m","reps":1,"arms":{"roles":[],"generic":true,"mechanical":false}}' "$BASE/api/runs")
[ "$code" = "400" ] || { echo "expected 400, got $code"; exit 1; }

echo "run"
ID=$(curl -fsS -X POST "${H[@]}" -d '{"provider":"demo-mock","model":"demo-mock-1","reps":1,"arms":{"roles":[],"generic":true,"mechanical":false}}' "$BASE/api/runs" | sed -E 's/.*"run_config_id": ?([0-9]+).*/\1/')
for i in $(seq 1 60); do
  STATE=$(curl -fsS "${H[@]}" "$BASE/api/runs/$ID/status" | sed -E 's/.*"state": ?"([^"]+)".*/\1/')
  [ "$STATE" != "running" ] && break
  sleep 2
done
[ "$STATE" = "completed" ] || { echo "run ended in state $STATE"; exit 1; }
echo "other visitor cannot read it"
code=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Session: someoneelse0000000000" "$BASE/api/runs/$ID/results")
[ "$code" = "404" ] || { echo "expected 404, got $code"; exit 1; }
echo "bundle verifies (real R, no LLM)"
curl -fsS -X POST "${H[@]}" "$BASE/api/runs/$ID/verify" >/dev/null
for i in $(seq 1 90); do
  V=$(curl -fsS "${H[@]}" "$BASE/api/runs/$ID/verify")
  echo "$V" | grep -q '"state": *"done"' && break
  sleep 3
done
echo "$V" | grep -q '"ok": *true' || { echo "verification failed: $V"; exit 1; }
echo "SMOKE TEST PASSED"
