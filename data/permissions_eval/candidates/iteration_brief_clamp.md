# Eval-loop iteration brief

Generated: `2026-08-05T08:04:37.469695+00:00`

- CM: `data/permissions_eval/confusion_matrices_clamp_20260803_no_defer_match.json`
- Protocol: `data/permissions_eval/eval_loop_protocol.json`
- Primary comparison: `anti_vs_adjudicated`

## Knob freeze (do not over-tune)

If macro-F1 ≥ promote/stop bar → **freeze** knobs for that field (unless documenting a held-out regression repair).

| Field | macro-F1 | bar | action | reason |
|---|---:|---:|---|---|
| `retrieve_permission` | 0.463 | 0.60 | **active** | macro_f1=0.463 < bar=0.600 |
| `mention_permission` | 1.000 | 0.95 | **monitor_only** | not a promotion driver |
| `factual_permission` | 0.497 | 0.65 | **active** | macro_f1=0.497 < bar=0.650 |
| `endorsement_permission` | 0.893 | 0.85 | **freeze** | macro_f1=0.893 >= bar=0.850 |
| `parasitic` | 0.809 | 0.75 | **freeze** | macro_f1=0.809 >= bar=0.750 |

**Freeze (no knob changes):** `endorsement_permission`, `parasitic`
**Active (may change knobs):** `retrieve_permission`, `factual_permission`
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
| `retrieve_permission` | 8 |
| `mention_permission` | 0 |
| `factual_permission` | 11 |
| `endorsement_permission` | 1 |
| `parasitic` | 3 |

### Active-field mismatches first

- [ACTIVE] `p01` `factual_permission`: gold=`attribute_only` system=`require_corroboration`
- [ACTIVE] `p03` `factual_permission`: gold=`attribute_only` system=`allow`
- [ACTIVE] `p13` `factual_permission`: gold=`attribute_only` system=`require_corroboration`
- [ACTIVE] `p14` `factual_permission`: gold=`attribute_only` system=`require_corroboration`
- [ACTIVE] `p15` `factual_permission`: gold=`attribute_only` system=`deny`
- [ACTIVE] `p24` `factual_permission`: gold=`attribute_only` system=`allow`
- [ACTIVE] `p25` `factual_permission`: gold=`attribute_only` system=`require_corroboration`
- [ACTIVE] `p26` `factual_permission`: gold=`require_corroboration` system=`attribute_only`
- [ACTIVE] `p27` `factual_permission`: gold=`attribute_only` system=`allow`
- [ACTIVE] `p29` `factual_permission`: gold=`attribute_only` system=`allow`
- [ACTIVE] `p33` `factual_permission`: gold=`require_corroboration` system=`allow`
- [ACTIVE] `p09` `retrieve_permission`: gold=`allow` system=`downrank`
- [ACTIVE] `p15` `retrieve_permission`: gold=`allow` system=`reject`
- [ACTIVE] `p19` `retrieve_permission`: gold=`allow` system=`downrank`
- [ACTIVE] `p21` `retrieve_permission`: gold=`downrank` system=`allow`
- [ACTIVE] `p22` `retrieve_permission`: gold=`downrank` system=`allow`
- [ACTIVE] `p23` `retrieve_permission`: gold=`allow` system=`downrank`
- [ACTIVE] `p25` `retrieve_permission`: gold=`downrank` system=`allow`
- [ACTIVE] `p33` `retrieve_permission`: gold=`downrank` system=`allow`
- [frozen-field] `p27` `endorsement_permission`: gold=`deny` system=`allow`
- [frozen-field] `p21` `parasitic`: gold=`none` system=`elevated`
- [frozen-field] `p23` `parasitic`: gold=`none` system=`elevated`
- [frozen-field] `p33` `parasitic`: gold=`elevated` system=`none`

## Next actions

1. Do **not** edit knobs for frozen fields.
2. Mine ACTIVE mismatches + LABEL_GUIDE (not system rationales) for hypotheses.
3. After a code change: re-run Anti-GEO on protocol sheets → `permissions_confusion.py` vs adjudicated.
4. Live Anti-GEO / blind API runs only when no other agent owns in-flight artifacts.

