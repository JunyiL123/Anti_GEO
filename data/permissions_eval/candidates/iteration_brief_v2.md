# Eval-loop iteration brief

Generated: `2026-08-05T09:35:47.191337+00:00`

- CM: `data/permissions_eval/confusion_matrices_v2_adjudicated.json`
- Protocol: `data/permissions_eval/eval_loop_protocol.json`
- Primary comparison: `anti_vs_adjudicated`

## Knob freeze (do not over-tune)

If macro-F1 ≥ promote/stop bar → **freeze** knobs for that field (unless documenting a held-out regression repair).

| Field | macro-F1 | bar | action | reason |
|---|---:|---:|---|---|
| `retrieve_permission` | 0.491 | 0.60 | **active** | macro_f1=0.491 < bar=0.600 |
| `mention_permission` | 0.430 | 0.95 | **monitor_only** | not a promotion driver |
| `factual_permission` | 0.320 | 0.65 | **active** | macro_f1=0.320 < bar=0.650 |
| `endorsement_permission` | 0.496 | 0.85 | **active** | macro_f1=0.496 < bar=0.850 |
| `parasitic` | 0.481 | 0.75 | **active** | macro_f1=0.481 < bar=0.750 |

**Freeze (no knob changes):** (none)
**Active (may change knobs):** `retrieve_permission`, `factual_permission`, `endorsement_permission`, `parasitic`
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
| `retrieve_permission` | 10 |
| `mention_permission` | 14 |
| `factual_permission` | 28 |
| `endorsement_permission` | 1 |
| `parasitic` | 3 |

### Active-field mismatches first

- [ACTIVE] `v2p26` `endorsement_permission`: gold=`deny` system=`allow`
- [ACTIVE] `v2p01` `factual_permission`: gold=`require_corroboration` system=`deny`
- [ACTIVE] `v2p02` `factual_permission`: gold=`attribute_only` system=`allow`
- [ACTIVE] `v2p03` `factual_permission`: gold=`allow` system=`attribute_only`
- [ACTIVE] `v2p05` `factual_permission`: gold=`attribute_only` system=`allow`
- [ACTIVE] `v2p08` `factual_permission`: gold=`require_corroboration` system=`deny`
- [ACTIVE] `v2p10` `factual_permission`: gold=`require_corroboration` system=`deny`
- [ACTIVE] `v2p11` `factual_permission`: gold=`require_corroboration` system=`deny`
- [ACTIVE] `v2p12` `factual_permission`: gold=`attribute_only` system=`deny`
- [ACTIVE] `v2p14` `factual_permission`: gold=`attribute_only` system=`deny`
- [ACTIVE] `v2p15` `factual_permission`: gold=`require_corroboration` system=`attribute_only`
- [ACTIVE] `v2p16` `factual_permission`: gold=`require_corroboration` system=`attribute_only`
- [ACTIVE] `v2p17` `factual_permission`: gold=`require_corroboration` system=`attribute_only`
- [ACTIVE] `v2p18` `factual_permission`: gold=`allow` system=`attribute_only`
- [ACTIVE] `v2p19` `factual_permission`: gold=`allow` system=`deny`
- [ACTIVE] `v2p20` `factual_permission`: gold=`attribute_only` system=`deny`
- [ACTIVE] `v2p23` `factual_permission`: gold=`allow` system=`deny`
- [ACTIVE] `v2p25` `factual_permission`: gold=`attribute_only` system=`deny`
- [ACTIVE] `v2p34` `factual_permission`: gold=`allow` system=`attribute_only`
- [ACTIVE] `v2p35` `factual_permission`: gold=`require_corroboration` system=`attribute_only`
- [ACTIVE] `v2p36` `factual_permission`: gold=`require_corroboration` system=`deny`
- [ACTIVE] `v2p37` `factual_permission`: gold=`attribute_only` system=`deny`
- [ACTIVE] `v2p38` `factual_permission`: gold=`attribute_only` system=`deny`
- [ACTIVE] `v2p39` `factual_permission`: gold=`attribute_only` system=`deny`
- [ACTIVE] `v2p41` `factual_permission`: gold=`allow` system=`attribute_only`
- [ACTIVE] `v2p50` `factual_permission`: gold=`allow` system=`attribute_only`
- [ACTIVE] `v2p51` `factual_permission`: gold=`allow` system=`deny`
- [ACTIVE] `v2p53` `factual_permission`: gold=`allow` system=`deny`
- [ACTIVE] `v2p55` `factual_permission`: gold=`attribute_only` system=`deny`
- [ACTIVE] `v2p12` `parasitic`: gold=`none` system=`elevated`
- [ACTIVE] `v2p14` `parasitic`: gold=`none` system=`elevated`
- [ACTIVE] `v2p35` `parasitic`: gold=`elevated` system=`none`
- [ACTIVE] `v2p01` `retrieve_permission`: gold=`downrank` system=`reject`
- [ACTIVE] `v2p12` `retrieve_permission`: gold=`allow` system=`downrank`
- [ACTIVE] `v2p13` `retrieve_permission`: gold=`downrank` system=`allow`
- [ACTIVE] `v2p19` `retrieve_permission`: gold=`allow` system=`reject`
- [ACTIVE] `v2p23` `retrieve_permission`: gold=`allow` system=`reject`
- [ACTIVE] `v2p33` `retrieve_permission`: gold=`downrank` system=`allow`
- [ACTIVE] `v2p34` `retrieve_permission`: gold=`allow` system=`downrank`
- [ACTIVE] `v2p43` `retrieve_permission`: gold=`allow` system=`downrank`
- [ACTIVE] `v2p45` `retrieve_permission`: gold=`allow` system=`downrank`
- [ACTIVE] `v2p57` `retrieve_permission`: gold=`allow` system=`downrank`
- [monitor] `v2p08` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v2p10` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v2p11` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v2p19` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v2p20` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v2p23` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v2p25` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v2p36` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v2p37` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v2p38` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v2p39` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v2p51` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v2p53` `mention_permission`: gold=`allow` system=`deny`
- [monitor] `v2p55` `mention_permission`: gold=`allow` system=`deny`

## Next actions

1. Do **not** edit knobs for frozen fields.
2. Mine ACTIVE mismatches + LABEL_GUIDE (not system rationales) for hypotheses.
3. After a code change: re-run Anti-GEO on protocol sheets → `permissions_confusion.py` vs adjudicated.
4. Live Anti-GEO / blind API runs only when no other agent owns in-flight artifacts.

