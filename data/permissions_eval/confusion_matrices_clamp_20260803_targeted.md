# Permissions confusion matrices (Mode A forced)

Generated: `2026-08-03T03:50:13.355871+00:00`

- Adjudication: `data/permissions_eval/label_sheet_v0_adjudication.json`
- Anti-GEO: `data/permissions_eval/label_sheet_v0_anti_geo_clamp_20260803_targeted.json`
- Parasitic Mode-B exclusions (Anti-GEO CMs): `p34, p36`

Five separate matrices per comparison (no fused score). `parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean.

## Summary — Anti-GEO vs Adjudicated (primary)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |
|---|---:|---:|---:|---:|---:|
| `endorsement_permission` | 18 | 0.944 | 0.818 | 0.640 | 0.056 |
| `parasitic` | 16 | 0.812 | 0.792 | 0.586 | 0.188 |
| `factual_permission` | 18 | 0.444 | 0.269 | 0.226 | 0.389 |
| `retrieve_permission` | 18 | 0.722 | 0.510 | 0.168 | 0.167 |
| `mention_permission` | 18 | 0.889 | 0.471 | 0.000 | 0.111 |

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

n=16; accuracy=0.812; macro-F1=0.792; κ_w²=0.586; off-by-one=0.188

| (rows=adjudicated) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 9 | 1 | 0 |
| elevated | 2 | 4 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p34, p36_

### `factual_permission`

n=18; accuracy=0.444; macro-F1=0.269; κ_w²=0.226; off-by-one=0.389

| (rows=adjudicated) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 0 | 0 | 0 | 0 |
| attribute_only | 3 | 6 | 1 | 2 |
| require_corroboration | 1 | 1 | 2 | 0 |
| deny | 0 | 0 | 2 | 0 |

### `retrieve_permission`

n=18; accuracy=0.722; macro-F1=0.510; κ_w²=0.168; off-by-one=0.167

| (rows=adjudicated) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 8 | 1 | 2 | 0 |
| downrank | 2 | 5 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=18; accuracy=0.889; macro-F1=0.471; κ_w²=0.000; off-by-one=0.111

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 16 | 2 |
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

n=16; accuracy=0.812; macro-F1=0.792; κ_w²=0.586; off-by-one=0.188

| (rows=human) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 9 | 1 | 0 |
| elevated | 2 | 4 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p34, p36_

### `factual_permission`

n=18; accuracy=0.333; macro-F1=0.209; κ_w²=0.104; off-by-one=0.500

| (rows=human) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 0 | 0 | 0 | 0 |
| attribute_only | 3 | 3 | 1 | 2 |
| require_corroboration | 1 | 4 | 3 | 0 |
| deny | 0 | 0 | 1 | 0 |

### `retrieve_permission`

n=18; accuracy=0.722; macro-F1=0.510; κ_w²=0.168; off-by-one=0.167

| (rows=human) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 8 | 1 | 2 | 0 |
| downrank | 2 | 5 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=18; accuracy=0.889; macro-F1=0.471; κ_w²=0.000; off-by-one=0.111

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 16 | 2 |
| deny | 0 | 0 |

## Anti-GEO vs LLM

### `endorsement_permission`

n=18; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 2 | 0 |
| deny | 0 | 16 |

### `parasitic`

n=16; accuracy=0.812; macro-F1=0.792; κ_w²=0.586; off-by-one=0.188

| (rows=llm) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 9 | 1 | 0 |
| elevated | 2 | 4 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p34, p36_

### `factual_permission`

n=18; accuracy=0.333; macro-F1=0.143; κ_w²=0.113; off-by-one=0.500

| (rows=llm) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 0 | 0 | 0 | 0 |
| attribute_only | 3 | 6 | 3 | 2 |
| require_corroboration | 1 | 1 | 0 | 0 |
| deny | 0 | 0 | 2 | 0 |

### `retrieve_permission`

n=18; accuracy=0.667; macro-F1=0.450; κ_w²=0.115; off-by-one=0.222

| (rows=llm) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 9 | 3 | 2 | 0 |
| downrank | 1 | 3 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=18; accuracy=0.889; macro-F1=0.471; κ_w²=0.000; off-by-one=0.111

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 16 | 2 |
| deny | 0 | 0 |

