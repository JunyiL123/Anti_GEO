# Permissions confusion matrices (Mode A forced)

Generated: `2026-07-27T12:49:11.452924+00:00`

- Adjudication: `data/permissions_eval/label_sheet_v0_adjudication.json`
- Anti-GEO: `data/permissions_eval/label_sheet_v0_anti_geo_fix_20260727_targeted.json`
- Parasitic Mode-B exclusions (Anti-GEO CMs): `(none)`

Five separate matrices per comparison (no fused score). `parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean.

## Summary — Anti-GEO vs Adjudicated (primary)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |
|---|---:|---:|---:|---:|---:|
| `endorsement_permission` | 18 | 0.944 | 0.818 | 0.640 | 0.056 |
| `parasitic` | 18 | 0.611 | 0.379 | -0.105 | 0.389 |
| `factual_permission` | 18 | 0.389 | 0.140 | -0.055 | 0.500 |
| `retrieve_permission` | 18 | 0.667 | 0.518 | 0.169 | 0.333 |
| `mention_permission` | 18 | 1.000 | 1.000 | 1.000 | 0.000 |

## Summary — Human vs LLM (label-noise ceiling)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ |
|---|---:|---:|---:|---:|
| `endorsement_permission` | 42 | 0.929 | 0.481 | 0.000 |
| `parasitic` | 42 | 0.976 | 0.959 | 0.919 |
| `factual_permission` | 42 | 0.714 | 0.680 | 0.711 |
| `retrieve_permission` | 42 | 0.857 | 0.768 | 0.543 |
| `mention_permission` | 42 | 1.000 | 1.000 | 1.000 |

## Anti-GEO vs Adjudicated (primary)

### `endorsement_permission`

n=18; accuracy=0.944; macro-F1=0.818; κ_w²=0.640; off-by-one=0.056

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 1 | 0 |
| deny | 1 | 16 |

### `parasitic`

n=18; accuracy=0.611; macro-F1=0.379; κ_w²=-0.105; off-by-one=0.389

| (rows=adjudicated) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 11 | 1 | 0 |
| elevated | 6 | 0 | 0 |
| suspected | 0 | 0 | 0 |

### `factual_permission`

n=18; accuracy=0.389; macro-F1=0.140; κ_w²=-0.055; off-by-one=0.500

| (rows=adjudicated) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 0 | 0 | 0 | 0 |
| attribute_only | 2 | 7 | 3 | 0 |
| require_corroboration | 0 | 4 | 0 | 0 |
| deny | 0 | 2 | 0 | 0 |

### `retrieve_permission`

n=18; accuracy=0.667; macro-F1=0.518; κ_w²=0.169; off-by-one=0.333

| (rows=adjudicated) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 11 | 0 | 0 | 0 |
| downrank | 6 | 1 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=18; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 18 | 0 |
| deny | 0 | 0 |

## Human vs LLM

### `endorsement_permission`

n=42; accuracy=0.929; macro-F1=0.481; κ_w²=0.000; off-by-one=0.071

| (rows=human) \ (cols=llm) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 3 | 39 |

### `parasitic`

n=42; accuracy=0.976; macro-F1=0.959; κ_w²=0.919; off-by-one=0.024

| (rows=human) \ (cols=llm) | none | elevated | suspected |
|---|---|---|---|
| none | 34 | 0 | 0 |
| elevated | 1 | 7 | 0 |
| suspected | 0 | 0 | 0 |

### `factual_permission`

n=42; accuracy=0.714; macro-F1=0.680; κ_w²=0.711; off-by-one=0.262

| (rows=human) \ (cols=llm) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 8 | 0 | 0 | 0 |
| attribute_only | 0 | 16 | 1 | 0 |
| require_corroboration | 0 | 9 | 5 | 1 |
| deny | 0 | 1 | 0 | 1 |

### `retrieve_permission`

n=42; accuracy=0.857; macro-F1=0.768; κ_w²=0.543; off-by-one=0.143

| (rows=human) \ (cols=llm) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 31 | 1 | 0 | 0 |
| downrank | 5 | 5 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=42; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=llm) | allow | deny |
|---|---|---|
| allow | 42 | 0 |
| deny | 0 | 0 |

## Anti-GEO vs Human

### `endorsement_permission`

n=18; accuracy=0.889; macro-F1=0.471; κ_w²=0.000; off-by-one=0.111

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 2 | 16 |

### `parasitic`

n=18; accuracy=0.611; macro-F1=0.379; κ_w²=-0.105; off-by-one=0.389

| (rows=human) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 11 | 1 | 0 |
| elevated | 6 | 0 | 0 |
| suspected | 0 | 0 | 0 |

### `factual_permission`

n=18; accuracy=0.222; macro-F1=0.091; κ_w²=-0.070; off-by-one=0.722

| (rows=human) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 0 | 0 | 0 | 0 |
| attribute_only | 2 | 4 | 3 | 0 |
| require_corroboration | 0 | 8 | 0 | 0 |
| deny | 0 | 1 | 0 | 0 |

### `retrieve_permission`

n=18; accuracy=0.667; macro-F1=0.518; κ_w²=0.169; off-by-one=0.333

| (rows=human) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 11 | 0 | 0 | 0 |
| downrank | 6 | 1 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=18; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 18 | 0 |
| deny | 0 | 0 |

## Anti-GEO vs LLM

### `endorsement_permission`

n=18; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 2 | 0 |
| deny | 0 | 16 |

### `parasitic`

n=18; accuracy=0.611; macro-F1=0.379; κ_w²=-0.105; off-by-one=0.389

| (rows=llm) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 11 | 1 | 0 |
| elevated | 6 | 0 | 0 |
| suspected | 0 | 0 | 0 |

### `factual_permission`

n=18; accuracy=0.500; macro-F1=0.167; κ_w²=-0.047; off-by-one=0.389

| (rows=llm) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 0 | 0 | 0 | 0 |
| attribute_only | 2 | 9 | 3 | 0 |
| require_corroboration | 0 | 2 | 0 | 0 |
| deny | 0 | 2 | 0 | 0 |

### `retrieve_permission`

n=18; accuracy=0.833; macro-F1=0.652; κ_w²=0.341; off-by-one=0.167

| (rows=llm) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 14 | 0 | 0 | 0 |
| downrank | 3 | 1 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=18; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 18 | 0 |
| deny | 0 | 0 |

