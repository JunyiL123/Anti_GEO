#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
OUT="data/permissions_eval/label_sheet_v0_anti_geo_full_rerun_20260724.json"
LOG="data/permissions_eval/label_sheet_v0_anti_geo_full_rerun_20260724.log"
PIDF="data/permissions_eval/label_sheet_v0_anti_geo_full_rerun_20260724.pid"
PY="/opt/homebrew/opt/python@3.11/bin/python3.11"
# skip p33 (headphonesty hang), p37 (Trustpilot); p32 already completed
IDS="p01,p02,p03,p04,p05,p06,p07,p08,p09,p10,p11,p12,p13,p14,p15,p16,p17,p18,p19,p20,p21,p22,p23,p24,p25,p26,p27,p28,p29,p30,p31,p32,p34,p35,p36,p38,p39,p40,p41,p42"

set -a
source "$ROOT/.env"
set +a
export PYTHONPATH=src
exec >>"$LOG" 2>&1
echo $$ > "$PIDF"
echo "RESUME $(date -u +%Y-%m-%dT%H:%M:%SZ) pid=$$ skip=p33,p37 --resume"
exec "$PY" -u demo/label_sheet_anti_geo.py \
  --sheet data/permissions_eval/label_sheet_v0.json \
  --engine azure --seed-limit 10 --max-verified 15 \
  --ids "$IDS" --resume --out "$OUT"
