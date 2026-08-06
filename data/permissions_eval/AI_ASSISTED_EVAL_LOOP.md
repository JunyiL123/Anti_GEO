# AI-assisted eval loop (honest “RLAIF-ish”)

Companion to [`eval_loop_protocol.json`](eval_loop_protocol.json). This is **not** RLHF/RLAIF (no preference model, no RL update). It is AI-assisted draft labeling + human adjudication + heuristic iteration.

**Live runs are off by default.** Build/run the thin demos anytime; do **not** start `label_sheet_anti_geo.py`, blind-judge API batches, or full-sheet CM campaigns while another agent owns in-flight `data/permissions_eval/` artifacts. Start a live iteration only after you confirm free paths.

---

## G0 protocol freeze

| Knob | Locked value |
|---|---|
| Gold | `label_sheet_v0_adjudication.json` (until a new adjudicated cut is promoted) |
| Mode A | forced cites (`--forced-cites`) |
| Mode B | `--mode-b-ugc` on |
| Intent | `commercial` |
| Skip IDs | `p37` (default; document any change) |
| Baseline CM | retune_20260727 |
| Current CM (calibration) | clamp_20260803_no_defer_match |
| Primary metric | Anti-GEO vs **adjudicated** (`anti_vs_adjudicated`) |
| Noise ceiling | Human vs LLM (`human_vs_llm`) |

Fair improvement: same gold × same protocol × full-sheet vs full-sheet. Do not promote on `anti_vs_llm`, defer-collapse-only tables, or targeted rematch *n* swaps.

---

## Gold pipeline

```text
LLM draft (LABEL_GUIDE + page/query only)
  → human adjudicate (accept / edit / reject)
  → adjudicated_labels = paper gold
Anti-GEO preds × adjudicated → paper CM / F1
raw LLM drafts → triage + Human–LLM noise ceiling only
```

**Never** optimize “until F1 vs LLM is very good.”

**Rubric-only drafts:** the blind judge must not see Anti-GEO heuristics, clamps, risk floats, mix shares, `llm_action`, or system pred JSON. Copying system logic into the labeler is circular.

---

## Stages

1. **G0** — Lock protocol (this card).
2. **G1** — Noise ceiling: human vs blind judge; fix judge if agreement collapses.
3. **G2** — Adjudicate disagreements (+ sample of agreements).
4. **G3** — Heuristic/clamp change from **error types vs adjudicated** → re-run system → CM vs named baseline.
5. **G4** — **Knob freeze:** only edit knobs for fields **below** promote/stop bar.
6. **G5** — Held-out adjudicated sheet never used for tuning this round.

---

## Promote / stop bars (macro-F1)

Prefer **held-out**; else frozen prior gold under the same protocol.

| Field | Bar | Role |
|---|---:|---|
| `endorsement_permission` | ≥0.85 | Hold / freeze knobs if above |
| `parasitic` | ≥0.75 | Hold / freeze knobs if above |
| `factual_permission` | ≥0.65 | Active gap |
| `retrieve_permission` | ≥0.60 | Active gap |
| `mention_permission` | monitor | Not a promotion driver |

**Knob freeze:** if field ≥ bar → do **not** change knobs aimed at that field (except documented held-out regression repair). On current clamp calibration: freeze endorsement + parasitic; work factual + retrieve only.

**Hard stop (any):** held-out plateau two rounds on factual+retrieve; residuals at Human–LLM noise ceiling; vanity F1 only (same IDs / defer tricks / empty-class macros); *n* too thin for more than pilot claims.

---

## Anti-overfit: rotate the eval set

Each iteration must change the candidate/eval pool (new queries/URLs). Do not tune forever on v0 IDs alone.

| Role | Behavior |
|---|---|
| Candidate pool | LLM query gen + new cites each round |
| Dev / triage | New draft→adjudicate rows for error mining |
| Frozen promotion gold | Prior adjudicated cut immutable for baseline CMs |
| Held-out | Never used to choose heuristic changes this round |
| System preds | Re-run Anti-GEO on sheets in play |

Cadence: add ~10–20 stratified commercial-intent pairs per iteration.

---

## Tooling (demos)

| Script | Role |
|---|---|
| [`demo/eval_loop_query_gen.py`](../../demo/eval_loop_query_gen.py) | Stratified candidate queries → pool (not gold) |
| [`demo/blind_label_judge.py`](../../demo/blind_label_judge.py) | LABEL_GUIDE-only draft labels |
| [`demo/eval_loop_disagreement.py`](../../demo/eval_loop_disagreement.py) | System vs draft disagreement export |
| [`demo/eval_loop_iteration_brief.py`](../../demo/eval_loop_iteration_brief.py) | Error buckets + knob-freeze brief |
| [`demo/label_sheet_anti_geo.py`](../../demo/label_sheet_anti_geo.py) | System preds — **invoke later, not during foreign in-flight runs**. Use `--freeze-referral-from <prior.json>` so Mode B referral mixes stay fixed across iterations (no rediscovery variance). New runs persist `predictions.referral_freeze`. |
| [`demo/permissions_confusion.py`](../../demo/permissions_confusion.py) | CMs |

Offline-safe defaults: `--dry-run` / offline CM inputs. No script auto-edits `src/anti_geo/`.

---

## Paper framing

**Claim-ready:** AI-assisted gold labeling: an LLM proposes draft permissions/parasitic labels from the labeling guide; a human adjudicates (accept/edit/reject) to produce evaluation gold; Anti-GEO is re-run as the system under test; primary CMs compare system predictions to adjudication; Human–LLM agreement is a label-noise ceiling; Group A (permissions) and Group B (parasitic) remain independent.

**Not claim-ready:** “RLHF/RLAIF,” “LLM labels are ground truth,” “LLM–system agreement validates correctness,” fused A+B F1, large-scale SOTA from pilot *n*≈40.
