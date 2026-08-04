#!/usr/bin/env bash
# Mode A forced-cites label-sheet eval (commercial + Mode B on UGC; skip p37).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
OUT="data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced.json"
LOG="data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced.log"
PIDF="data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced.pid"
PY="/opt/homebrew/opt/python@3.11/bin/python3.11"

set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a
export PYTHONPATH=src

exec >>"$LOG" 2>&1
echo $$ > "$PIDF"
echo "START $(date -u +%Y-%m-%dT%H:%M:%SZ) pid=$$ mode_a_forced skip=p37 --resume"
exec "$PY" -u demo/label_sheet_anti_geo.py \
  --sheet data/permissions_eval/label_sheet_v0.json \
  --engine azure \
  --intent commercial \
  --forced-cites \
  --mode-b-ugc \
  --skip-ids p37 \
  --seed-limit 10 \
  --max-verified 15 \
  --resume \
  --out "$OUT"
