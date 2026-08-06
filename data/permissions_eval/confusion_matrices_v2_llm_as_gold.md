# Permissions confusion matrices (Mode A forced)

Generated: `2026-08-05T08:54:52.337651+00:00`

- Adjudication: `data/permissions_eval/label_sheet_v2_adjudication_llm_as_gold_no_defer.json`
- Anti-GEO: `data/permissions_eval/label_sheet_v2_anti_geo_mode_a_forced_no_defer.json`
- Parasitic Mode-B exclusions (Anti-GEO CMs): `v2p01, v2p19, v2p23`

Five separate matrices per comparison (no fused score). `parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean.

## Summary — Anti-GEO vs Adjudicated (primary)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |
|---|---:|---:|---:|---:|---:|
| `endorsement_permission` | 38 | 0.974 | 0.493 | 0.000 | 0.026 |
| `parasitic` | 35 | 0.943 | 0.485 | 0.000 | 0.057 |
| `factual_permission` | 38 | 0.737 | 0.515 | 0.222 | 0.132 |
| `retrieve_permission` | 38 | 0.632 | 0.402 | -0.014 | 0.289 |
| `mention_permission` | 38 | 0.947 | 0.486 | 0.000 | 0.053 |

## Summary — Human vs LLM (label-noise ceiling)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ |
|---|---:|---:|---:|---:|
| `endorsement_permission` | 0 | n/a | n/a | n/a |
| `parasitic` | 0 | n/a | n/a | n/a |
| `factual_permission` | 0 | n/a | n/a | n/a |
| `retrieve_permission` | 0 | n/a | n/a | n/a |
| `mention_permission` | 0 | n/a | n/a | n/a |

## Anti-GEO vs Adjudicated (primary)

### `endorsement_permission`

n=38; accuracy=0.974; macro-F1=0.493; κ_w²=0.000; off-by-one=0.026

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 1 | 37 |

### `parasitic`

n=35; accuracy=0.943; macro-F1=0.485; κ_w²=0.000; off-by-one=0.057

| (rows=adjudicated) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 33 | 2 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v2p01, v2p19, v2p23_

### `factual_permission`

n=38; accuracy=0.737; macro-F1=0.515; κ_w²=0.222; off-by-one=0.132

| (rows=adjudicated) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 9 | 4 | 0 | 2 |
| attribute_only | 1 | 19 | 0 | 3 |
| require_corroboration | 0 | 0 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=38; accuracy=0.632; macro-F1=0.402; κ_w²=-0.014; off-by-one=0.289

| (rows=adjudicated) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 19 | 6 | 0 | 3 |
| downrank | 5 | 5 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=38; accuracy=0.947; macro-F1=0.486; κ_w²=0.000; off-by-one=0.053

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 36 | 2 |
| deny | 0 | 0 |

## Human vs LLM

### `endorsement_permission`

n=0; accuracy=n/a; macro-F1=n/a; κ_w²=n/a; off-by-one=n/a

| (rows=human) \ (cols=llm) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 0 | 0 |

### `parasitic`

n=0; accuracy=n/a; macro-F1=n/a; κ_w²=n/a; off-by-one=n/a

| (rows=human) \ (cols=llm) | none | elevated | suspected |
|---|---|---|---|
| none | 0 | 0 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v2p01, v2p02, v2p04, v2p05, v2p06, v2p09, v2p10, v2p11, v2p12, v2p13, v2p14, v2p18, v2p19, v2p21, v2p23, v2p24, v2p25, v2p26, v2p27, v2p28, v2p29, v2p30, v2p31, v2p32, v2p33, v2p34, v2p37, v2p39, v2p40, v2p41, v2p42, v2p43, v2p44, v2p45, v2p46, v2p47, v2p48, v2p49, v2p50, v2p51, v2p52, v2p53, v2p54, v2p55, v2p56, v2p57_

### `factual_permission`

n=0; accuracy=n/a; macro-F1=n/a; κ_w²=n/a; off-by-one=n/a

| (rows=human) \ (cols=llm) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 0 | 0 | 0 | 0 |
| attribute_only | 0 | 0 | 0 | 0 |
| require_corroboration | 0 | 0 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=0; accuracy=n/a; macro-F1=n/a; κ_w²=n/a; off-by-one=n/a

| (rows=human) \ (cols=llm) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 0 | 0 | 0 | 0 |
| downrank | 0 | 0 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=0; accuracy=n/a; macro-F1=n/a; κ_w²=n/a; off-by-one=n/a

| (rows=human) \ (cols=llm) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 0 | 0 |

## Anti-GEO vs Human

### `endorsement_permission`

n=0; accuracy=n/a; macro-F1=n/a; κ_w²=n/a; off-by-one=n/a

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 0 | 0 |

### `parasitic`

n=0; accuracy=n/a; macro-F1=n/a; κ_w²=n/a; off-by-one=n/a

| (rows=human) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 0 | 0 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v2p01, v2p02, v2p04, v2p05, v2p06, v2p09, v2p12, v2p13, v2p14, v2p18, v2p19, v2p21, v2p23, v2p24, v2p26, v2p27, v2p28, v2p29, v2p30, v2p31, v2p32, v2p33, v2p34, v2p40, v2p41, v2p42, v2p43, v2p44, v2p45, v2p46, v2p47, v2p48, v2p49, v2p50, v2p52, v2p54, v2p56, v2p57_

### `factual_permission`

n=0; accuracy=n/a; macro-F1=n/a; κ_w²=n/a; off-by-one=n/a

| (rows=human) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 0 | 0 | 0 | 0 |
| attribute_only | 0 | 0 | 0 | 0 |
| require_corroboration | 0 | 0 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=0; accuracy=n/a; macro-F1=n/a; κ_w²=n/a; off-by-one=n/a

| (rows=human) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 0 | 0 | 0 | 0 |
| downrank | 0 | 0 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=0; accuracy=n/a; macro-F1=n/a; κ_w²=n/a; off-by-one=n/a

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 0 | 0 |

## Anti-GEO vs LLM

### `endorsement_permission`

n=38; accuracy=0.974; macro-F1=0.493; κ_w²=0.000; off-by-one=0.026

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 1 | 37 |

### `parasitic`

n=35; accuracy=0.943; macro-F1=0.485; κ_w²=0.000; off-by-one=0.057

| (rows=llm) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 33 | 2 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v2p01, v2p19, v2p23_

### `factual_permission`

n=38; accuracy=0.737; macro-F1=0.515; κ_w²=0.222; off-by-one=0.132

| (rows=llm) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 9 | 4 | 0 | 2 |
| attribute_only | 1 | 19 | 0 | 3 |
| require_corroboration | 0 | 0 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=38; accuracy=0.632; macro-F1=0.402; κ_w²=-0.014; off-by-one=0.289

| (rows=llm) \ (cols=anti) | allow | downrank | defer | reject |
|---|---|---|---|---|
| allow | 19 | 6 | 0 | 3 |
| downrank | 5 | 5 | 0 | 0 |
| defer | 0 | 0 | 0 | 0 |
| reject | 0 | 0 | 0 | 0 |

### `mention_permission`

n=38; accuracy=0.947; macro-F1=0.486; κ_w²=0.000; off-by-one=0.053

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 36 | 2 |
| deny | 0 | 0 |

