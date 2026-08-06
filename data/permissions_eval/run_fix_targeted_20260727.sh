#!/usr/bin/env bash
# Targeted rematch after soft-prior kill + retrieve/factual fixes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a
export PYTHONPATH=src
export ANTI_GEO_FETCH_HEADED=0

OUT="data/permissions_eval/label_sheet_v0_anti_geo_fix_20260727_targeted.json"
LOG="data/permissions_eval/label_sheet_v0_anti_geo_fix_20260727_targeted.log"
PIDF="data/permissions_eval/label_sheet_v0_anti_geo_fix_20260727_targeted.pid"
IDS="p01,p10,p13,p14,p17,p18,p22,p23,p26,p27,p29,p33,p34,p36,p38,p39,p40,p41"

echo $$ > "$PIDF"
echo "START $(date -u +%Y-%m-%dT%H:%M:%SZ) pid=$$ out=$OUT ids=$IDS"
python3 demo/label_sheet_anti_geo.py \
  --forced-cites \
  --mode-b-ugc \
  --engine azure \
  --intent commercial \
  --ids "$IDS" \
  --skip-ids p37 \
  --resume \
  --out "$OUT" \
  2>&1 | tee -a "$LOG"
echo "END $(date -u +%Y-%m-%dT%H:%M:%SZ) exit=$?"
