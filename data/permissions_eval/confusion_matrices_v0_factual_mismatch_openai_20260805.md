# Permissions confusion matrices (Mode A forced)

Generated: `2026-08-05T06:43:07.849485+00:00`

- Adjudication: `data/permissions_eval/label_sheet_v0_adjudication.json`
- Anti-GEO: `data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_factual_mismatch_openai_20260805_no_defer.json`
- Parasitic Mode-B exclusions (Anti-GEO CMs): `p15`

Five separate matrices per comparison (no fused score). `parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean.

## Summary — Anti-GEO vs Adjudicated (primary)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |
|---|---:|---:|---:|---:|---:|
| `endorsement_permission` | 36 | 0.917 | 0.678 | 0.357 | 0.083 |
| `parasitic` | 35 | 0.914 | 0.809 | 0.618 | 0.086 |
| `factual_permission` | 36 | 0.917 | 0.660 | 0.662 | 0.028 |
| `retrieve_permission` | 36 | 0.778 | 0.463 | 0.182 | 0.194 |
| `mention_permission` | 36 | 1.000 | 1.000 | 1.000 | 0.000 |

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

n=36; accuracy=0.917; macro-F1=0.678; κ_w²=0.357; off-by-one=0.083

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 1 | 1 |
| deny | 2 | 32 |

### `parasitic`

n=35; accuracy=0.914; macro-F1=0.809; κ_w²=0.618; off-by-one=0.086

| (rows=adjudicated) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 29 | 2 | 0 |
| elevated | 1 | 3 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p15_

### `factual_permission`

n=36; accuracy=0.917; macro-F1=0.660; κ_w²=0.662; off-by-one=0.028

| (rows=adjudicated) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 7 | 0 | 0 | 0 |
| attribute_only | 0 | 23 | 0 | 1 |
| require_corroboration | 1 | 1 | 3 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=36; accuracy=0.778; macro-F1=0.463; κ_w²=0.182; off-by-one=0.194

| (rows=adjudicated) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 24 | 3 | 0 | 1 |
| downrank | 4 | 4 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=36; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 36 | 0 |
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

n=36; accuracy=0.917; macro-F1=0.478; κ_w²=0.000; off-by-one=0.083

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 3 | 33 |

### `parasitic`

n=35; accuracy=0.914; macro-F1=0.809; κ_w²=0.618; off-by-one=0.086

| (rows=human) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 29 | 2 | 0 |
| elevated | 1 | 3 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p15_

### `factual_permission`

n=36; accuracy=0.722; macro-F1=0.536; κ_w²=0.500; off-by-one=0.194

| (rows=human) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 7 | 0 | 0 | 0 |
| attribute_only | 0 | 16 | 0 | 1 |
| require_corroboration | 1 | 7 | 3 | 0 |
| deny | 0 | 1 | 0 | 0 |

### `retrieve_permission`

n=36; accuracy=0.806; macro-F1=0.483; κ_w²=0.215; off-by-one=0.167

| (rows=human) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 25 | 3 | 0 | 1 |
| downrank | 3 | 4 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=36; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 36 | 0 |
| deny | 0 | 0 |

## Anti-GEO vs LLM

### `endorsement_permission`

n=36; accuracy=0.944; macro-F1=0.818; κ_w²=0.636; off-by-one=0.056

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 2 | 1 |
| deny | 1 | 32 |

### `parasitic`

n=35; accuracy=0.914; macro-F1=0.809; κ_w²=0.618; off-by-one=0.086

| (rows=llm) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 29 | 2 | 0 |
| elevated | 1 | 3 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p15_

### `factual_permission`

n=36; accuracy=0.806; macro-F1=0.453; κ_w²=0.466; off-by-one=0.139

| (rows=llm) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 7 | 0 | 0 | 0 |
| attribute_only | 0 | 22 | 3 | 1 |
| require_corroboration | 1 | 2 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=36; accuracy=0.750; macro-F1=0.351; κ_w²=0.019; off-by-one=0.222

| (rows=llm) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 26 | 6 | 0 | 1 |
| downrank | 2 | 1 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=36; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 36 | 0 |
| deny | 0 | 0 |

