#!/usr/bin/env bash
# Two-shard Mode A forced retune. Args: a|b
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
SHARD="${1:?usage: $0 a|b}"
STAMP="retune_20260727"
PY="/opt/homebrew/opt/python@3.11/bin/python3.11"

# Query-balanced: A = mattress+weight+moisturizer+VPN (18); B = rest (23, skip p37)
IDS_A="p01,p02,p03,p04,p05,p06,p07,p08,p09,p10,p11,p12,p13,p14,p15,p16,p17,p18"
IDS_B="p19,p20,p21,p22,p23,p24,p25,p26,p27,p28,p29,p30,p31,p32,p33,p34,p35,p36,p38,p39,p40,p41,p42"

if [[ "$SHARD" == "a" ]]; then
  IDS="$IDS_A"
  OUT="data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_${STAMP}_shard_a.json"
  # Seed from the interrupted single-run progress (p01–p08 ok).
  SEED="data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_${STAMP}.json"
  if [[ -f "$SEED" && ! -f "$OUT" ]]; then
    cp "$SEED" "$OUT"
  fi
  RESUME_FLAG=1
elif [[ "$SHARD" == "b" ]]; then
  IDS="$IDS_B"
  OUT="data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_${STAMP}_shard_b.json"
  RESUME_FLAG=1
else
  echo "shard must be a or b" >&2
  exit 1
fi

LOG="${OUT%.json}.log"
PIDF="${OUT%.json}.pid"

set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a
export PYTHONPATH=src
# Avoid headed Chrome CF retries — Trustpilot/CF popups block the eval.
export ANTI_GEO_FETCH_HEADED=0

exec >>"$LOG" 2>&1
echo $$ > "$PIDF"
echo "START $(date -u +%Y-%m-%dT%H:%M:%SZ) pid=$$ shard=$SHARD out=$OUT ids=$IDS"
CMD=(
  caffeinate -dims "$PY" -u demo/label_sheet_anti_geo.py
  --sheet data/permissions_eval/label_sheet_v0.json
  --engine azure
  --intent commercial
  --forced-cites
  --mode-b-ugc
  --skip-ids p37
  --ids "$IDS"
  --seed-limit 10
  --max-verified 15
  --out "$OUT"
)
if [[ "$RESUME_FLAG" -eq 1 ]]; then
  CMD+=(--resume)
fi
exec "${CMD[@]}"
