# Eval-loop iteration brief

Generated: `2026-08-06T06:17:48.143862+00:00`

- CM: `data/permissions_eval/confusion_matrices_v3_iter1.json`
- Protocol: `data/permissions_eval/eval_loop_protocol.json`
- Primary comparison: `anti_vs_adjudicated`

## Knob freeze (do not over-tune)

If macro-F1 ≥ promote/stop bar → **freeze** knobs for that field (unless documenting a held-out regression repair).

| Field | macro-F1 | bar | action | reason |
|---|---:|---:|---|---|
| `retrieve_permission` | 0.505 | 0.60 | **active** | macro_f1=0.505 < bar=0.600 |
| `mention_permission` | 0.422 | 0.95 | **monitor_only** | not a promotion driver |
| `factual_permission` | 0.406 | 0.65 | **active** | macro_f1=0.406 < bar=0.650 |
| `endorsement_permission` | 0.924 | 0.85 | **freeze** | macro_f1=0.924 >= bar=0.850 |
| `parasitic` | 0.469 | 0.75 | **active** | macro_f1=0.469 < bar=0.750 |

**Freeze (no knob changes):** `endorsement_permission`
**Active (may change knobs):** `retrieve_permission`, `factual_permission`, `parasitic`
**Monitor only:** `mention_permission`

## Rotation reminder

- Add new queries/URLs this iteration (candidate pool).
- Do not tune only on frozen v0 IDs.
- Held-out adjudicated rows are never used to choose knobs this round.

## Paper framing

**Claim-ready:** AI-assisted gold labeling: an LLM proposes draft permissions/parasitic labels from LABEL_GUIDE only; a human adjudicates (accept/edit/reject) to produce evaluation gold; Anti-GEO is re-run as the system under test; primary CMs compare system predictions to adjudication; Human–LLM agreement is a label-noise ceiling; Group A and Group B remain independent.

**Not claim-ready:** `RLHF/RLAIF`; `LLM labels are ground truth`; `LLM–system agreement validates correctness`; `fused A+B F1`; `large-scale SOTA from pilot n≈40`

## Error buckets (Anti-GEO vs adjudicated)

| Field | n mismatches |
|---|---:|
| `retrieve_permission` | 12 |
| `mention_permission` | 16 |
| `factual_permission` | 9 |
| `endorsement_permission` | 1 |
| `parasitic` | 7 |

### Active-field mismatches first

- [ACTIVE] `v3p04` `factual_permission`: gold=`attribute_only` system=`require_corroboration`
- [ACTIVE] `v3p15` `factual_permission`: gold=`allow` system=`attribute_only`
- [ACTIVE] `v3p18` `factual_permission`: gold=`allow` system=`attribute_only`
- [ACTIVE] `v3p26` `factual_permission`: gold=`deny` system=`attribute_only`
- [ACTIVE] `v3p27` `factual_permission`: gold=`require_corroboration` system=`attribute_only`
- [ACTIVE] `v3p28` `factual_permission`: gold=`require_corroboration` system=`attribute_only`
- [ACTIVE] `v3p33` `factual_permission`: gold=`require_corroboration` system=`attribute_only`
- [ACTIVE] `v3p45` `factual_permission`: gold=`allow` system=`attribute_only`
- [ACTIVE] `v3p48` `factual_permission`: gold=`allow` system=`attribute_only`
- [ACTIVE] `v3p04` `parasitic`: gold=`none` system=`elevated`
- [ACTIVE] `v3p20` `parasitic`: gold=`none` system=`elevated`
- [ACTIVE] `v3p26` `parasitic`: gold=`suspected` system=`none`
- [ACTIVE] `v3p27` `parasitic`: gold=`suspected` system=`none`
- [ACTIVE] `v3p33` `parasitic`: gold=`elevated` system=`none`
- [ACTIVE] `v3p35` `parasitic`: gold=`none` system=`elevated`
- [ACTIVE] `v3p46` `parasitic`: gold=`none` system=`elevated`
- [ACTIVE] `v3p04` `retrieve_permission`: gold=`downrank` system=`allow`
- [ACTIVE] `v3p14` `retrieve_permission`: gold=`allow` system=`downrank`
- [ACTIVE] `v3p16` `retrieve_permission`: gold=`allow` system=`downrank`
- [ACTIVE] `v3p20` `retrieve_permission`: gold=`downrank` system=`allow`
- [ACTIVE] `v3p26` `retrieve_permission`: gold=`downrank` system=`allow`
- [ACTIVE] `v3p27` `retrieve_permission`: gold=`downrank` system=`allow`
- [ACTIVE] `v3p29` `retrieve_permission`: gold=`allow` system=`downrank`
- [ACTIVE] `v3p32` `retrieve_permission`: gold=`allow` system=`downrank`
- [ACTIVE] `v3p33` `retrieve_permission`: gold=`downrank` system=`allow`
- [ACTIVE] `v3p35` `retrieve_permission`: gold=`allow` system=`downrank`
- [ACTIVE] `v3p45` `retrieve_permission`: gold=`allow` system=`downrank`
- [ACTIVE] `v3p46` `retrieve_permission`: gold=`allow` system=`downrank`
- [frozen-field] `v3p36` `endorsement_permission`: gold=`allow` system=`deny`
- [monitor] `v3p03` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p06` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p10` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p11` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p12` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p15` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p26` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p27` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p37` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p39` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p40` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p41` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p50` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p51` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p52` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v3p54` `mention_permission`: gold=`allow` system=`deny`

## Next actions

1. Do **not** edit knobs for frozen fields.
2. Mine ACTIVE mismatches + LABEL_GUIDE (not system rationales) for hypotheses.
3. After a code change: re-run Anti-GEO on protocol sheets → `permissions_confusion.py` vs adjudicated.
4. Live Anti-GEO / blind API runs only when no other agent owns in-flight artifacts.

