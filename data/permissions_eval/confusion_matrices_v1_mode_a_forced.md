# Permissions confusion matrices (Mode A forced)

Generated: `2026-08-04T10:22:13.839066+00:00`

- Adjudication: `data/permissions_eval/label_sheet_v1_adjudication.json`
- Anti-GEO: `data/permissions_eval/label_sheet_v1_anti_geo_mode_a_forced.json`
- Parasitic Mode-B exclusions (Anti-GEO CMs): `v1p20, v1p33`

Five separate matrices per comparison (no fused score). `parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean.

## Summary — Anti-GEO vs Adjudicated (primary)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |
|---|---:|---:|---:|---:|---:|
| `endorsement_permission` | 47 | 0.830 | 0.746 | 0.492 | 0.170 |
| `parasitic` | 45 | 0.956 | 0.489 | 0.000 | 0.044 |
| `factual_permission` | 47 | 0.511 | 0.262 | 0.174 | 0.426 |
| `retrieve_permission` | 47 | 0.787 | 0.357 | 0.256 | 0.191 |
| `mention_permission` | 47 | 0.957 | 0.489 | 0.000 | 0.043 |

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

n=47; accuracy=0.830; macro-F1=0.746; κ_w²=0.492; off-by-one=0.170

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 6 | 4 |
| deny | 4 | 33 |

### `parasitic`

n=45; accuracy=0.956; macro-F1=0.489; κ_w²=0.000; off-by-one=0.044

| (rows=adjudicated) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 43 | 2 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v1p20, v1p33_

### `factual_permission`

n=47; accuracy=0.511; macro-F1=0.262; κ_w²=0.174; off-by-one=0.426

| (rows=adjudicated) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 6 | 0 | 1 | 0 |
| attribute_only | 15 | 18 | 5 | 2 |
| require_corroboration | 0 | 0 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=47; accuracy=0.787; macro-F1=0.357; κ_w²=0.256; off-by-one=0.191

| (rows=adjudicated) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 36 | 7 | 1 | 0 |
| downrank | 1 | 1 | 1 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=47; accuracy=0.957; macro-F1=0.489; κ_w²=0.000; off-by-one=0.043

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 45 | 2 |
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

n=47; accuracy=0.830; macro-F1=0.746; κ_w²=0.492; off-by-one=0.170

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 6 | 4 |
| deny | 4 | 33 |

### `parasitic`

n=45; accuracy=0.956; macro-F1=0.489; κ_w²=0.000; off-by-one=0.044

| (rows=human) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 43 | 2 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v1p20, v1p33_

### `factual_permission`

n=47; accuracy=0.468; macro-F1=0.239; κ_w²=0.143; off-by-one=0.468

| (rows=human) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 5 | 0 | 1 | 0 |
| attribute_only | 16 | 17 | 5 | 2 |
| require_corroboration | 0 | 1 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=47; accuracy=0.809; macro-F1=0.367; κ_w²=0.293; off-by-one=0.170

| (rows=human) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 37 | 7 | 1 | 0 |
| downrank | 0 | 1 | 1 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=47; accuracy=0.957; macro-F1=0.489; κ_w²=0.000; off-by-one=0.043

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 45 | 2 |
| deny | 0 | 0 |

## Anti-GEO vs LLM

### `endorsement_permission`

n=47; accuracy=0.851; macro-F1=0.785; κ_w²=0.571; off-by-one=0.149

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 7 | 4 |
| deny | 3 | 33 |

### `parasitic`

n=45; accuracy=0.956; macro-F1=0.489; κ_w²=0.000; off-by-one=0.044

| (rows=llm) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 43 | 2 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v1p20, v1p33_

### `factual_permission`

n=47; accuracy=0.511; macro-F1=0.262; κ_w²=0.174; off-by-one=0.426

| (rows=llm) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 6 | 0 | 1 | 0 |
| attribute_only | 15 | 18 | 5 | 2 |
| require_corroboration | 0 | 0 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=47; accuracy=0.787; macro-F1=0.357; κ_w²=0.256; off-by-one=0.191

| (rows=llm) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 36 | 7 | 1 | 0 |
| downrank | 1 | 1 | 1 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=47; accuracy=0.957; macro-F1=0.489; κ_w²=0.000; off-by-one=0.043

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 45 | 2 |
| deny | 0 | 0 |

