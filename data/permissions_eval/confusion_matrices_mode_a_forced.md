# Permissions confusion matrices (Mode A forced)

Generated: `2026-07-24T09:43:58.957760+00:00`

- Adjudication: `data/permissions_eval/label_sheet_v0_adjudication.json`
- Anti-GEO: `data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced.json`
- Parasitic Mode-B exclusions (Anti-GEO CMs): `p15, p30`

Five separate matrices per comparison (no fused score). `parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean.

## Summary — Anti-GEO vs Adjudicated (primary)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |
|---|---:|---:|---:|---:|---:|
| `endorsement_permission` | 41 | 0.850 | 0.459 | -0.043 | 0.150 |
| `parasitic` | 39 | 0.744 | 0.426 | -0.140 | 0.256 |
| `factual_permission` | 41 | 0.683 | 0.407 | 0.430 | 0.220 |
| `retrieve_permission` | 41 | 0.439 | 0.187 | -0.097 | 0.537 |
| `mention_permission` | 41 | 0.976 | 0.494 | 0.000 | 0.024 |

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

n=41; accuracy=0.850; macro-F1=0.459; κ_w²=-0.043; off-by-one=0.150

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 1 |
| deny | 5 | 34 |

### `parasitic`

n=39; accuracy=0.744; macro-F1=0.426; κ_w²=-0.140; off-by-one=0.256

| (rows=adjudicated) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 29 | 4 | 0 |
| elevated | 6 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p15, p30_

### `factual_permission`

n=41; accuracy=0.683; macro-F1=0.407; κ_w²=0.430; off-by-one=0.220

| (rows=adjudicated) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 8 | 0 | 0 | 0 |
| attribute_only | 2 | 20 | 1 | 1 |
| require_corroboration | 1 | 5 | 0 | 1 |
| deny | 0 | 2 | 0 | 0 |

### `retrieve_permission`

n=41; accuracy=0.439; macro-F1=0.187; κ_w²=-0.097; off-by-one=0.537

| (rows=adjudicated) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 16 | 13 | 0 | 1 |
| downrank | 8 | 2 | 1 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=41; accuracy=0.976; macro-F1=0.494; κ_w²=0.000; off-by-one=0.024

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 40 | 1 |
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

n=41; accuracy=0.854; macro-F1=0.461; κ_w²=0.000; off-by-one=0.146

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 6 | 35 |

### `parasitic`

n=39; accuracy=0.769; macro-F1=0.524; κ_w²=0.059; off-by-one=0.231

| (rows=human) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 29 | 3 | 0 |
| elevated | 6 | 1 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p15, p30_

### `factual_permission`

n=41; accuracy=0.512; macro-F1=0.358; κ_w²=0.395; off-by-one=0.390

| (rows=human) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 8 | 0 | 0 | 0 |
| attribute_only | 2 | 13 | 1 | 1 |
| require_corroboration | 1 | 12 | 0 | 1 |
| deny | 0 | 2 | 0 | 0 |

### `retrieve_permission`

n=41; accuracy=0.415; macro-F1=0.165; κ_w²=-0.133; off-by-one=0.561

| (rows=human) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 16 | 14 | 0 | 1 |
| downrank | 8 | 1 | 1 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=41; accuracy=0.976; macro-F1=0.494; κ_w²=0.000; off-by-one=0.024

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 40 | 1 |
| deny | 0 | 0 |

## Anti-GEO vs LLM

### `endorsement_permission`

n=41; accuracy=0.829; macro-F1=0.563; κ_w²=0.138; off-by-one=0.171

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 1 | 2 |
| deny | 5 | 33 |

### `parasitic`

n=39; accuracy=0.744; macro-F1=0.426; κ_w²=-0.140; off-by-one=0.256

| (rows=llm) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 29 | 4 | 0 |
| elevated | 6 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): p15, p30_

### `factual_permission`

n=41; accuracy=0.780; macro-F1=0.511; κ_w²=0.491; off-by-one=0.122

| (rows=llm) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 8 | 0 | 0 | 0 |
| attribute_only | 2 | 23 | 0 | 1 |
| require_corroboration | 1 | 2 | 1 | 1 |
| deny | 0 | 2 | 0 | 0 |

### `retrieve_permission`

n=41; accuracy=0.561; macro-F1=0.226; κ_w²=0.076; off-by-one=0.415

| (rows=llm) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 21 | 13 | 0 | 1 |
| downrank | 3 | 2 | 1 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=41; accuracy=0.976; macro-F1=0.494; κ_w²=0.000; off-by-one=0.024

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 40 | 1 |
| deny | 0 | 0 |

