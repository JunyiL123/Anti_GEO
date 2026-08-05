# Permissions confusion matrices (Mode A forced)

Generated: `2026-08-05T09:35:47.141290+00:00`

- Adjudication: `data/permissions_eval/label_sheet_v2_adjudication.json`
- Anti-GEO: `data/permissions_eval/label_sheet_v2_anti_geo_mode_a_forced.json`
- Parasitic Mode-B exclusions (Anti-GEO CMs): `v2p01, v2p08, v2p10, v2p11, v2p19, v2p20, v2p23, v2p25, v2p36, v2p37, v2p38, v2p39, v2p51, v2p53, v2p55`

Five separate matrices per comparison (no fused score). `parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean. `retrieve_permission` rows where gold or pred is `defer` are excluded (fetch gate, not scored as a use-rights class).

## Summary — Anti-GEO vs Adjudicated (primary)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |
|---|---:|---:|---:|---:|---:|
| `endorsement_permission` | 57 | 0.982 | 0.496 | 0.000 | 0.018 |
| `parasitic` | 42 | 0.929 | 0.481 | -0.033 | 0.071 |
| `factual_permission` | 57 | 0.509 | 0.320 | 0.241 | 0.281 |
| `retrieve_permission` | 40 | 0.750 | 0.491 | 0.360 | 0.200 |
| `mention_permission` | 57 | 0.754 | 0.430 | 0.000 | 0.246 |

## Summary — Human vs LLM (label-noise ceiling)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ |
|---|---:|---:|---:|---:|
| `endorsement_permission` | 2 | 1.000 | 1.000 | 1.000 |
| `parasitic` | 2 | 1.000 | 1.000 | 1.000 |
| `factual_permission` | 2 | 0.500 | 0.333 | -0.333 |
| `retrieve_permission` | 3 | 0.000 | 0.000 | 0.000 |
| `mention_permission` | 2 | 1.000 | 1.000 | 1.000 |

## Anti-GEO vs Adjudicated (primary)

### `endorsement_permission`

n=57; accuracy=0.982; macro-F1=0.496; κ_w²=0.000; off-by-one=0.018

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 1 | 56 |

### `parasitic`

n=42; accuracy=0.929; macro-F1=0.481; κ_w²=-0.033; off-by-one=0.071

| (rows=adjudicated) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 39 | 2 | 0 |
| elevated | 1 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v2p01, v2p08, v2p10, v2p11, v2p19, v2p20, v2p23, v2p25, v2p36, v2p37, v2p38, v2p39, v2p51, v2p53, v2p55_

### `factual_permission`

n=57; accuracy=0.509; macro-F1=0.320; κ_w²=0.241; off-by-one=0.281

| (rows=adjudicated) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 8 | 5 | 0 | 4 |
| attribute_only | 2 | 21 | 0 | 8 |
| require_corroboration | 0 | 4 | 0 | 5 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=40; accuracy=0.750; macro-F1=0.491; κ_w²=0.360; off-by-one=0.200

| (rows=adjudicated) \ (cols=anti) | allow | downrank | reject |
|---|---|---|---|
| allow | 23 | 5 | 2 |
| downrank | 2 | 7 | 1 |
| reject | 0 | 0 | 0 |

_Skipped (retrieve defer on gold or pred): v2p08, v2p10, v2p11, v2p15, v2p16, v2p17, v2p20, v2p22, v2p25, v2p35, v2p36, v2p37, v2p38, v2p39, v2p51, v2p53, v2p55_

### `mention_permission`

n=57; accuracy=0.754; macro-F1=0.430; κ_w²=0.000; off-by-one=0.246

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 43 | 14 |
| deny | 0 | 0 |

## Human vs LLM

### `endorsement_permission`

n=2; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=llm) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 0 | 2 |

### `parasitic`

n=2; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=llm) | none | elevated | suspected |
|---|---|---|---|
| none | 2 | 0 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v2p01, v2p02, v2p04, v2p05, v2p07, v2p08, v2p09, v2p10, v2p11, v2p12, v2p13, v2p14, v2p15, v2p16, v2p17, v2p18, v2p19, v2p20, v2p21, v2p22, v2p23, v2p24, v2p25, v2p26, v2p27, v2p28, v2p29, v2p30, v2p31, v2p32, v2p33, v2p34, v2p35, v2p36, v2p37, v2p38, v2p39, v2p40, v2p41, v2p42, v2p43, v2p44, v2p45, v2p46, v2p47, v2p48, v2p49, v2p50, v2p51, v2p52, v2p53, v2p54, v2p55, v2p56, v2p57_

### `factual_permission`

n=2; accuracy=0.500; macro-F1=0.333; κ_w²=-0.333; off-by-one=0.000

| (rows=human) \ (cols=llm) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 0 | 0 | 1 | 0 |
| attribute_only | 0 | 1 | 0 | 0 |
| require_corroboration | 0 | 0 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=3; accuracy=0.000; macro-F1=0.000; κ_w²=0.000; off-by-one=1.000

| (rows=human) \ (cols=llm) | allow | downrank | reject |
|---|---|---|---|
| allow | 0 | 3 | 0 |
| downrank | 0 | 0 | 0 |
| reject | 0 | 0 | 0 |

_Skipped (retrieve defer on gold or pred): v2p01, v2p02, v2p03, v2p04, v2p05, v2p07, v2p08, v2p09, v2p10, v2p11, v2p12, v2p13, v2p14, v2p15, v2p16, v2p17, v2p18, v2p19, v2p20, v2p21, v2p22, v2p23, v2p24, v2p25, v2p26, v2p27, v2p28, v2p29, v2p30, v2p31, v2p32, v2p33, v2p34, v2p35, v2p36, v2p37, v2p38, v2p39, v2p40, v2p41, v2p42, v2p43, v2p44, v2p45, v2p46, v2p48, v2p50, v2p51, v2p52, v2p53, v2p54, v2p55, v2p56, v2p57_

### `mention_permission`

n=2; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=llm) | allow | deny |
|---|---|---|
| allow | 2 | 0 |
| deny | 0 | 0 |

## Anti-GEO vs Human

### `endorsement_permission`

n=2; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 0 | 2 |

### `parasitic`

n=2; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 2 | 0 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v2p01, v2p02, v2p04, v2p05, v2p07, v2p08, v2p09, v2p10, v2p11, v2p12, v2p13, v2p14, v2p15, v2p16, v2p17, v2p18, v2p19, v2p20, v2p21, v2p22, v2p23, v2p24, v2p25, v2p26, v2p27, v2p28, v2p29, v2p30, v2p31, v2p32, v2p33, v2p34, v2p35, v2p36, v2p37, v2p38, v2p39, v2p40, v2p41, v2p42, v2p43, v2p44, v2p45, v2p46, v2p47, v2p48, v2p49, v2p50, v2p51, v2p52, v2p53, v2p54, v2p55, v2p56, v2p57_

### `factual_permission`

n=2; accuracy=0.500; macro-F1=0.333; κ_w²=0.000; off-by-one=0.500

| (rows=human) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 0 | 1 | 0 | 0 |
| attribute_only | 0 | 1 | 0 | 0 |
| require_corroboration | 0 | 0 | 0 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=5; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=anti) | allow | downrank | reject |
|---|---|---|---|
| allow | 4 | 0 | 0 |
| downrank | 0 | 1 | 0 |
| reject | 0 | 0 | 0 |

_Skipped (retrieve defer on gold or pred): v2p01, v2p02, v2p04, v2p05, v2p08, v2p09, v2p10, v2p11, v2p12, v2p13, v2p14, v2p15, v2p16, v2p17, v2p18, v2p19, v2p20, v2p21, v2p22, v2p23, v2p24, v2p25, v2p26, v2p27, v2p28, v2p29, v2p30, v2p31, v2p32, v2p33, v2p34, v2p35, v2p36, v2p37, v2p38, v2p39, v2p40, v2p41, v2p42, v2p43, v2p44, v2p45, v2p46, v2p48, v2p50, v2p51, v2p52, v2p53, v2p54, v2p55, v2p56, v2p57_

### `mention_permission`

n=2; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 2 | 0 |
| deny | 0 | 0 |

## Anti-GEO vs LLM

### `endorsement_permission`

n=57; accuracy=0.982; macro-F1=0.496; κ_w²=0.000; off-by-one=0.018

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 1 | 56 |

### `parasitic`

n=42; accuracy=0.929; macro-F1=0.481; κ_w²=-0.033; off-by-one=0.071

| (rows=llm) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 39 | 2 | 0 |
| elevated | 1 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v2p01, v2p08, v2p10, v2p11, v2p19, v2p20, v2p23, v2p25, v2p36, v2p37, v2p38, v2p39, v2p51, v2p53, v2p55_

### `factual_permission`

n=57; accuracy=0.526; macro-F1=0.339; κ_w²=0.223; off-by-one=0.246

| (rows=llm) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 9 | 4 | 0 | 4 |
| attribute_only | 1 | 21 | 0 | 9 |
| require_corroboration | 0 | 5 | 0 | 4 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=38; accuracy=0.632; macro-F1=0.402; κ_w²=0.044; off-by-one=0.289

| (rows=llm) \ (cols=anti) | allow | downrank | reject |
|---|---|---|---|
| allow | 19 | 6 | 3 |
| downrank | 5 | 5 | 0 |
| reject | 0 | 0 | 0 |

_Skipped (retrieve defer on gold or pred): v2p03, v2p07, v2p08, v2p10, v2p11, v2p15, v2p16, v2p17, v2p20, v2p22, v2p25, v2p35, v2p36, v2p37, v2p38, v2p39, v2p51, v2p53, v2p55_

### `mention_permission`

n=57; accuracy=0.754; macro-F1=0.430; κ_w²=0.000; off-by-one=0.246

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 43 | 14 |
| deny | 0 | 0 |

