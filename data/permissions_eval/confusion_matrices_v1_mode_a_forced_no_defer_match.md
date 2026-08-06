# Permissions confusion matrices (Mode A forced)

Generated: `2026-08-05T06:43:08.089476+00:00`

- Adjudication: `data/permissions_eval/label_sheet_v1_adjudication.json`
- Anti-GEO: `data/permissions_eval/label_sheet_v1_anti_geo_mode_a_forced_no_defer_match.json`
- Parasitic Mode-B exclusions (Anti-GEO CMs): `(none)`

Five separate matrices per comparison (no fused score). `parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean.

## Summary — Anti-GEO vs Adjudicated (primary)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |
|---|---:|---:|---:|---:|---:|
| `endorsement_permission` | 44 | 0.818 | 0.741 | 0.482 | 0.182 |
| `parasitic` | 44 | 0.955 | 0.488 | 0.000 | 0.045 |
| `factual_permission` | 44 | 0.545 | 0.361 | 0.176 | 0.432 |
| `retrieve_permission` | 44 | 0.818 | 0.450 | -0.041 | 0.182 |
| `mention_permission` | 44 | 1.000 | 1.000 | 1.000 | 0.000 |

## Summary — Human vs LLM (label-noise ceiling)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ |
|---|---:|---:|---:|---:|
| `endorsement_permission` | 47 | 0.894 | 0.847 | 0.694 |
| `parasitic` | 47 | 1.000 | 1.000 | 1.000 |
| `factual_permission` | 47 | 0.957 | 0.633 | 0.840 |
| `retrieve_permission` | 47 | 0.979 | 0.894 | 0.789 |
| `mention_permission` | 47 | 1.000 | 1.000 | 1.000 |

## Anti-GEO vs Adjudicated (primary)

### `endorsement_permission`

n=44; accuracy=0.818; macro-F1=0.741; κ_w²=0.482; off-by-one=0.182

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 6 | 4 |
| deny | 4 | 30 |

### `parasitic`

n=44; accuracy=0.955; macro-F1=0.488; κ_w²=0.000; off-by-one=0.045

| (rows=adjudicated) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 42 | 2 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

### `factual_permission`

n=44; accuracy=0.545; macro-F1=0.361; κ_w²=0.176; off-by-one=0.432

| (rows=adjudicated) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 6 | 0 | 1 | 0 |
| attribute_only | 15 | 18 | 4 | 0 |
| require_corroboration | 0 | 0 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=44; accuracy=0.818; macro-F1=0.450; κ_w²=-0.041; off-by-one=0.182

| (rows=adjudicated) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 36 | 7 | 0 | 0 |
| downrank | 1 | 0 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=44; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 44 | 0 |
| deny | 0 | 0 |

## Human vs LLM

### `endorsement_permission`

n=47; accuracy=0.894; macro-F1=0.847; κ_w²=0.694; off-by-one=0.106

| (rows=human) \ (cols=llm) | allow | deny |
|---|---|---|
| allow | 8 | 2 |
| deny | 3 | 34 |

### `parasitic`

n=47; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=llm) | none | elevated | suspected |
|---|---|---|---|
| none | 47 | 0 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

### `factual_permission`

n=47; accuracy=0.957; macro-F1=0.633; κ_w²=0.840; off-by-one=0.043

| (rows=human) \ (cols=llm) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 6 | 0 | 0 | 0 |
| attribute_only | 1 | 39 | 0 | 0 |
| require_corroboration | 0 | 1 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=47; accuracy=0.979; macro-F1=0.894; κ_w²=0.789; off-by-one=0.021

| (rows=human) \ (cols=llm) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 44 | 1 | 0 | 0 |
| downrank | 0 | 2 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=47; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=llm) | allow | deny |
|---|---|---|
| allow | 47 | 0 |
| deny | 0 | 0 |

## Anti-GEO vs Human

### `endorsement_permission`

n=44; accuracy=0.818; macro-F1=0.741; κ_w²=0.482; off-by-one=0.182

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 6 | 4 |
| deny | 4 | 30 |

### `parasitic`

n=44; accuracy=0.955; macro-F1=0.488; κ_w²=0.000; off-by-one=0.045

| (rows=human) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 42 | 2 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

### `factual_permission`

n=44; accuracy=0.500; macro-F1=0.330; κ_w²=0.149; off-by-one=0.477

| (rows=human) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 5 | 0 | 1 | 0 |
| attribute_only | 16 | 17 | 4 | 0 |
| require_corroboration | 0 | 1 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=44; accuracy=0.841; macro-F1=0.457; κ_w²=0.000; off-by-one=0.159

| (rows=human) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 37 | 7 | 0 | 0 |
| downrank | 0 | 0 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=44; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 44 | 0 |
| deny | 0 | 0 |

## Anti-GEO vs LLM

### `endorsement_permission`

n=44; accuracy=0.841; macro-F1=0.781; κ_w²=0.562; off-by-one=0.159

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 7 | 4 |
| deny | 3 | 30 |

### `parasitic`

n=44; accuracy=0.955; macro-F1=0.488; κ_w²=0.000; off-by-one=0.045

| (rows=llm) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 42 | 2 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

### `factual_permission`

n=44; accuracy=0.545; macro-F1=0.361; κ_w²=0.176; off-by-one=0.432

| (rows=llm) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 6 | 0 | 1 | 0 |
| attribute_only | 15 | 18 | 4 | 0 |
| require_corroboration | 0 | 0 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=44; accuracy=0.818; macro-F1=0.450; κ_w²=-0.041; off-by-one=0.182

| (rows=llm) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 36 | 7 | 0 | 0 |
| downrank | 1 | 0 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=44; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 44 | 0 |
| deny | 0 | 0 |

