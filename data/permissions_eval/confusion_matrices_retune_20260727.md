# Permissions confusion matrices (Mode A forced)

Generated: `2026-07-27T10:07:52.373540+00:00`

- Adjudication: `data/permissions_eval/label_sheet_v0_adjudication.json`
- Anti-GEO: `data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_retune_20260727.json`
- Parasitic Mode-B exclusions (Anti-GEO CMs): `p15, p28, p34, p36, p42`

Five separate matrices per comparison (no fused score). `parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean.

## Summary — Anti-GEO vs Adjudicated (primary)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |
|---|---:|---:|---:|---:|---:|
| `endorsement_permission` | 41 | 0.976 | 0.827 | 0.655 | 0.024 |
| `parasitic` | 36 | 0.639 | 0.453 | -0.083 | 0.361 |
| `factual_permission` | 41 | 0.610 | 0.362 | 0.215 | 0.195 |
| `retrieve_permission` | 41 | 0.439 | 0.204 | -0.093 | 0.463 |
| `mention_permission` | 41 | 0.902 | 0.474 | 0.000 | 0.098 |

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

n=41; accuracy=0.976; macro-F1=0.827; κ_w²=0.655; off-by-one=0.024

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 1 | 1 |
| deny | 0 | 39 |

### `parasitic`

n=36; accuracy=0.639; macro-F1=0.453; κ_w²=-0.083; off-by-one=0.361

| (rows=adjudicated) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 22 | 8 | 0 |
| elevated | 5 | 1 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p15, p28, p34, p36, p42_

### `factual_permission`

n=41; accuracy=0.610; macro-F1=0.362; κ_w²=0.215; off-by-one=0.195

| (rows=adjudicated) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 7 | 1 | 0 | 0 |
| attribute_only | 2 | 18 | 1 | 3 |
| require_corroboration | 3 | 2 | 0 | 2 |
| deny | 1 | 1 | 0 | 0 |

### `retrieve_permission`

n=41; accuracy=0.439; macro-F1=0.204; κ_w²=-0.093; off-by-one=0.463

| (rows=adjudicated) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 15 | 11 | 3 | 1 |
| downrank | 7 | 3 | 1 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=41; accuracy=0.902; macro-F1=0.474; κ_w²=0.000; off-by-one=0.098

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 37 | 4 |
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

n=41; accuracy=0.976; macro-F1=0.494; κ_w²=0.000; off-by-one=0.024

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 1 | 40 |

### `parasitic`

n=36; accuracy=0.639; macro-F1=0.453; κ_w²=-0.083; off-by-one=0.361

| (rows=human) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 22 | 8 | 0 |
| elevated | 5 | 1 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p15, p28, p34, p36, p42_

### `factual_permission`

n=41; accuracy=0.439; macro-F1=0.308; κ_w²=0.200; off-by-one=0.366

| (rows=human) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 7 | 1 | 0 | 0 |
| attribute_only | 2 | 11 | 1 | 3 |
| require_corroboration | 3 | 9 | 0 | 2 |
| deny | 1 | 1 | 0 | 0 |

### `retrieve_permission`

n=41; accuracy=0.415; macro-F1=0.183; κ_w²=-0.114; off-by-one=0.488

| (rows=human) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 15 | 12 | 3 | 1 |
| downrank | 7 | 2 | 1 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=41; accuracy=0.902; macro-F1=0.474; κ_w²=0.000; off-by-one=0.098

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 37 | 4 |
| deny | 0 | 0 |

## Anti-GEO vs LLM

### `endorsement_permission`

n=41; accuracy=0.951; macro-F1=0.737; κ_w²=0.481; off-by-one=0.049

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 1 | 2 |
| deny | 0 | 38 |

### `parasitic`

n=36; accuracy=0.639; macro-F1=0.453; κ_w²=-0.083; off-by-one=0.361

| (rows=llm) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 22 | 8 | 0 |
| elevated | 5 | 1 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p15, p28, p34, p36, p42_

### `factual_permission`

n=41; accuracy=0.634; macro-F1=0.438; κ_w²=0.256; off-by-one=0.195

| (rows=llm) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 7 | 1 | 0 | 0 |
| attribute_only | 4 | 18 | 0 | 4 |
| require_corroboration | 1 | 2 | 1 | 1 |
| deny | 1 | 1 | 0 | 0 |

### `retrieve_permission`

n=41; accuracy=0.537; macro-F1=0.242; κ_w²=-0.035; off-by-one=0.341

| (rows=llm) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 19 | 11 | 4 | 1 |
| downrank | 3 | 3 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=41; accuracy=0.902; macro-F1=0.474; κ_w²=0.000; off-by-one=0.098

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 37 | 4 |
| deny | 0 | 0 |

