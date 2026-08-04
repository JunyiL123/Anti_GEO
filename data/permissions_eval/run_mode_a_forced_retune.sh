#!/usr/bin/env bash
# Mode A forced-cites re-eval after detector retune (new out JSON; skip p37).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
STAMP="retune_$(date -u +%Y%m%d)"
OUT="data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_${STAMP}.json"
LOG="data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_${STAMP}.log"
PIDF="data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_${STAMP}.pid"
PY="/opt/homebrew/opt/python@3.11/bin/python3.11"

set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a
export PYTHONPATH=src

exec >>"$LOG" 2>&1
echo $$ > "$PIDF"
echo "START $(date -u +%Y-%m-%dT%H:%M:%SZ) pid=$$ mode_a_forced_retune skip=p37 out=$OUT"
exec caffeinate -dims "$PY" -u demo/label_sheet_anti_geo.py \
  --sheet data/permissions_eval/label_sheet_v0.json \
  --engine azure \
  --intent commercial \
  --forced-cites \
  --mode-b-ugc \
  --skip-ids p37 \
  --seed-limit 10 \
  --max-verified 15 \
  --out "$OUT"
