# Permissions confusion matrices (Mode A forced)

Generated: `2026-08-05T11:15:58.950201+00:00`

- Adjudication: `data/permissions_eval/label_sheet_v2_adjudication.json`
- Anti-GEO: `data/permissions_eval/label_sheet_v2_anti_geo_mode_a_forced_iter2.json`
- Parasitic Mode-B exclusions (Anti-GEO CMs): `v2p01, v2p06, v2p08, v2p10, v2p11, v2p13, v2p20, v2p36, v2p37, v2p38, v2p39, v2p51, v2p53, v2p55`

Five separate matrices per comparison (no fused score). `parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean. `retrieve_permission` rows where gold or pred is `defer` are excluded (fetch gate, not scored as a use-rights class).

## Summary — Anti-GEO vs Adjudicated (primary)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |
|---|---:|---:|---:|---:|---:|
| `endorsement_permission` | 57 | 1.000 | 1.000 | 1.000 | 0.000 |
| `parasitic` | 43 | 0.930 | 0.482 | -0.032 | 0.070 |
| `factual_permission` | 57 | 0.649 | 0.415 | 0.554 | 0.351 |
| `retrieve_permission` | 40 | 0.800 | 0.480 | 0.529 | 0.200 |
| `mention_permission` | 57 | 0.772 | 0.436 | 0.000 | 0.228 |

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

n=57; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 0 | 57 |

### `parasitic`

n=43; accuracy=0.930; macro-F1=0.482; κ_w²=-0.032; off-by-one=0.070

| (rows=adjudicated) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 40 | 2 | 0 |
| elevated | 1 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v2p01, v2p06, v2p08, v2p10, v2p11, v2p13, v2p20, v2p36, v2p37, v2p38, v2p39, v2p51, v2p53, v2p55_

### `factual_permission`

n=57; accuracy=0.649; macro-F1=0.415; κ_w²=0.554; off-by-one=0.351

| (rows=adjudicated) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 9 | 8 | 0 | 0 |
| attribute_only | 2 | 26 | 3 | 0 |
| require_corroboration | 0 | 6 | 2 | 1 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=40; accuracy=0.800; macro-F1=0.480; κ_w²=0.529; off-by-one=0.200

| (rows=adjudicated) \ (cols=anti) | allow | downrank | reject |
|---|---|---|---|
| allow | 27 | 3 | 0 |
| downrank | 4 | 5 | 1 |
| reject | 0 | 0 | 0 |

_Skipped (retrieve defer on gold or pred): v2p06, v2p10, v2p11, v2p13, v2p15, v2p16, v2p17, v2p20, v2p22, v2p35, v2p36, v2p37, v2p38, v2p39, v2p51, v2p53, v2p55_

### `mention_permission`

n=57; accuracy=0.772; macro-F1=0.436; κ_w²=0.000; off-by-one=0.228

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 44 | 13 |
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

n=1; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=human) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 1 | 0 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v2p01, v2p02, v2p04, v2p05, v2p06, v2p07, v2p08, v2p09, v2p10, v2p11, v2p12, v2p13, v2p14, v2p15, v2p16, v2p17, v2p18, v2p19, v2p20, v2p21, v2p22, v2p23, v2p24, v2p25, v2p26, v2p27, v2p28, v2p29, v2p30, v2p31, v2p32, v2p33, v2p34, v2p35, v2p36, v2p37, v2p38, v2p39, v2p40, v2p41, v2p42, v2p43, v2p44, v2p45, v2p46, v2p47, v2p48, v2p49, v2p50, v2p51, v2p52, v2p53, v2p54, v2p55, v2p56, v2p57_

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

_Skipped (retrieve defer on gold or pred): v2p01, v2p02, v2p04, v2p05, v2p06, v2p09, v2p10, v2p11, v2p12, v2p13, v2p14, v2p15, v2p16, v2p17, v2p18, v2p19, v2p20, v2p21, v2p22, v2p23, v2p24, v2p25, v2p26, v2p27, v2p28, v2p29, v2p30, v2p31, v2p32, v2p33, v2p34, v2p35, v2p36, v2p37, v2p38, v2p39, v2p40, v2p41, v2p42, v2p43, v2p44, v2p45, v2p46, v2p48, v2p50, v2p51, v2p52, v2p53, v2p54, v2p55, v2p56, v2p57_

### `mention_permission`

n=2; accuracy=0.500; macro-F1=0.333; κ_w²=0.000; off-by-one=0.500

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 1 | 1 |
| deny | 0 | 0 |

## Anti-GEO vs LLM

### `endorsement_permission`

n=57; accuracy=1.000; macro-F1=1.000; κ_w²=1.000; off-by-one=0.000

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 0 | 57 |

### `parasitic`

n=43; accuracy=0.930; macro-F1=0.482; κ_w²=-0.032; off-by-one=0.070

| (rows=llm) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 40 | 2 | 0 |
| elevated | 1 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v2p01, v2p06, v2p08, v2p10, v2p11, v2p13, v2p20, v2p36, v2p37, v2p38, v2p39, v2p51, v2p53, v2p55_

### `factual_permission`

n=57; accuracy=0.667; macro-F1=0.433; κ_w²=0.510; off-by-one=0.316

| (rows=llm) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 10 | 7 | 0 | 0 |
| attribute_only | 1 | 26 | 3 | 1 |
| require_corroboration | 0 | 7 | 2 | 0 |
| deny | 0 | 0 | 0 | 0 |

### `retrieve_permission`

n=37; accuracy=0.757; macro-F1=0.447; κ_w²=0.232; off-by-one=0.216

| (rows=llm) \ (cols=anti) | allow | downrank | reject |
|---|---|---|---|
| allow | 24 | 3 | 1 |
| downrank | 5 | 4 | 0 |
| reject | 0 | 0 | 0 |

_Skipped (retrieve defer on gold or pred): v2p03, v2p06, v2p07, v2p08, v2p10, v2p11, v2p13, v2p15, v2p16, v2p17, v2p20, v2p22, v2p35, v2p36, v2p37, v2p38, v2p39, v2p51, v2p53, v2p55_

### `mention_permission`

n=57; accuracy=0.772; macro-F1=0.436; κ_w²=0.000; off-by-one=0.228

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 44 | 13 |
| deny | 0 | 0 |

