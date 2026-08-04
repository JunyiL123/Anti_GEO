# Permissions confusion matrices (Mode A forced)

Generated: `2026-08-03T07:35:55.394358+00:00`

- Adjudication: `data/permissions_eval/label_sheet_v0_adjudication.json`
- Anti-GEO: `data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_rf_20260803.json`
- Parasitic Mode-B exclusions (Anti-GEO CMs): `p02, p15, p42`

Five separate matrices per comparison (no fused score). `parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean.

## Summary — Anti-GEO vs Adjudicated (primary)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |
|---|---:|---:|---:|---:|---:|
| `endorsement_permission` | 41 | 0.976 | 0.894 | 0.788 | 0.024 |
| `parasitic` | 38 | 0.921 | 0.861 | 0.722 | 0.079 |
| `factual_permission` | 41 | 0.756 | 0.746 | 0.706 | 0.195 |
| `retrieve_permission` | 41 | 0.780 | 0.495 | 0.276 | 0.195 |
| `mention_permission` | 41 | 1.000 | 1.000 | 1.000 | 0.000 |

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

n=41; accuracy=0.976; macro-F1=0.894; κ_w²=0.788; off-by-one=0.024

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 2 | 0 |
| deny | 1 | 38 |

### `parasitic`

n=38; accuracy=0.921; macro-F1=0.861; κ_w²=0.722; off-by-one=0.079

| (rows=adjudicated) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 30 | 2 | 0 |
| elevated | 1 | 5 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p02, p15, p42_

### `factual_permission`

n=41; accuracy=0.756; macro-F1=0.746; κ_w²=0.706; off-by-one=0.195

| (rows=adjudicated) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 8 | 0 | 0 | 0 |
| attribute_only | 5 | 17 | 1 | 1 |
| require_corroboration | 1 | 2 | 4 | 0 |
| deny | 0 | 0 | 0 | 2 |

### `retrieve_permission`

n=41; accuracy=0.780; macro-F1=0.495; κ_w²=0.276; off-by-one=0.195

| (rows=adjudicated) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 25 | 4 | 0 | 1 |
| downrank | 4 | 7 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=41; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 41 | 0 |
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

n=41; accuracy=0.927; macro-F1=0.481; κ_w²=0.000; off-by-one=0.073

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 3 | 38 |

### `parasitic`

n=38; accuracy=0.921; macro-F1=0.861; κ_w²=0.722; off-by-one=0.079

| (rows=human) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 30 | 2 | 0 |
| elevated | 1 | 5 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p02, p15, p42_

### `factual_permission`

n=41; accuracy=0.561; macro-F1=0.526; κ_w²=0.568; off-by-one=0.366

| (rows=human) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 8 | 0 | 0 | 0 |
| attribute_only | 5 | 10 | 1 | 1 |
| require_corroboration | 1 | 8 | 4 | 1 |
| deny | 0 | 1 | 0 | 1 |

### `retrieve_permission`

n=41; accuracy=0.805; macro-F1=0.511; κ_w²=0.309; off-by-one=0.171

| (rows=human) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 26 | 4 | 0 | 1 |
| downrank | 3 | 7 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=41; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 41 | 0 |
| deny | 0 | 0 |

## Anti-GEO vs LLM

### `endorsement_permission`

n=41; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 3 | 0 |
| deny | 0 | 38 |

### `parasitic`

n=38; accuracy=0.921; macro-F1=0.861; κ_w²=0.722; off-by-one=0.079

| (rows=llm) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 30 | 2 | 0 |
| elevated | 1 | 5 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p02, p15, p42_

### `factual_permission`

n=41; accuracy=0.707; macro-F1=0.671; κ_w²=0.655; off-by-one=0.244

| (rows=llm) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 8 | 0 | 0 | 0 |
| attribute_only | 5 | 17 | 3 | 1 |
| require_corroboration | 1 | 2 | 2 | 0 |
| deny | 0 | 0 | 0 | 2 |

### `retrieve_permission`

n=41; accuracy=0.756; macro-F1=0.438; κ_w²=0.178; off-by-one=0.220

| (rows=llm) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 27 | 7 | 0 | 1 |
| downrank | 2 | 4 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=41; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 41 | 0 |
| deny | 0 | 0 |

