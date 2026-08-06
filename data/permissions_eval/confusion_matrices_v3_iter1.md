# Permissions confusion matrices (Mode A forced)

Generated: `2026-08-06T06:17:48.089358+00:00`

- Adjudication: `data/permissions_eval/label_sheet_v3_adjudication.json`
- Anti-GEO: `data/permissions_eval/label_sheet_v3_anti_geo_mode_a_forced_iter1.json`
- Parasitic Mode-B exclusions (Anti-GEO CMs): `v3p03, v3p06, v3p10, v3p11, v3p12, v3p15, v3p26, v3p27, v3p37, v3p39, v3p40, v3p41, v3p50, v3p51, v3p52, v3p54`

Five separate matrices per comparison (no fused score). `parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean. `retrieve_permission` rows where gold or pred is `defer` are excluded (fetch gate, not scored as a use-rights class).

## Summary — Anti-GEO vs Adjudicated (primary)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |
|---|---:|---:|---:|---:|---:|
| `endorsement_permission` | 59 | 0.983 | 0.924 | 0.848 | 0.017 |
| `parasitic` | 43 | 0.884 | 0.469 | -0.039 | 0.116 |
| `factual_permission` | 59 | 0.847 | 0.406 | 0.441 | 0.136 |
| `retrieve_permission` | 52 | 0.769 | 0.505 | 0.013 | 0.231 |
| `mention_permission` | 59 | 0.729 | 0.422 | 0.000 | 0.271 |

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

n=59; accuracy=0.983; macro-F1=0.924; κ_w²=0.848; off-by-one=0.017

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 3 | 1 |
| deny | 0 | 55 |

### `parasitic`

n=43; accuracy=0.884; macro-F1=0.469; κ_w²=-0.039; off-by-one=0.116

| (rows=adjudicated) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 38 | 4 | 0 |
| elevated | 1 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v3p03, v3p06, v3p10, v3p11, v3p12, v3p15, v3p26, v3p27, v3p37, v3p39, v3p40, v3p41, v3p50, v3p51, v3p52, v3p54_

### `factual_permission`

n=59; accuracy=0.847; macro-F1=0.406; κ_w²=0.441; off-by-one=0.136

| (rows=adjudicated) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 5 | 4 | 0 | 0 |
| attribute_only | 0 | 45 | 1 | 0 |
| require_corroboration | 0 | 3 | 0 | 0 |
| deny | 0 | 1 | 0 | 0 |

### `retrieve_permission`

n=52; accuracy=0.769; macro-F1=0.505; κ_w²=0.013; off-by-one=0.231

| (rows=adjudicated) \ (cols=anti) | allow | downrank | reject |
|---|---|---|---|
| allow | 39 | 7 | 0 |
| downrank | 5 | 1 | 0 |
| reject | 0 | 0 | 0 |

_Skipped (retrieve defer on gold or pred): v3p03, v3p06, v3p15, v3p37, v3p39, v3p40, v3p41_

### `mention_permission`

n=59; accuracy=0.729; macro-F1=0.422; κ_w²=0.000; off-by-one=0.271

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 43 | 16 |
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

_Skipped (Mode B missing or null): v3p01, v3p02, v3p03, v3p04, v3p05, v3p06, v3p07, v3p08, v3p09, v3p10, v3p11, v3p12, v3p13, v3p14, v3p15, v3p16, v3p17, v3p18, v3p19, v3p20, v3p21, v3p22, v3p23, v3p24, v3p25, v3p26, v3p27, v3p28, v3p29, v3p30, v3p31, v3p32, v3p33, v3p34, v3p35, v3p36, v3p37, v3p38, v3p39, v3p40, v3p41, v3p42, v3p43, v3p44, v3p45, v3p46, v3p47, v3p48, v3p49, v3p50, v3p51, v3p52, v3p53, v3p54, v3p55, v3p56, v3p57, v3p58, v3p59_

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

| (rows=human) \ (cols=llm) | allow | downrank | reject |
|---|---|---|---|
| allow | 0 | 0 | 0 |
| downrank | 0 | 0 | 0 |
| reject | 0 | 0 | 0 |

_Skipped (retrieve defer on gold or pred): v3p01, v3p02, v3p03, v3p04, v3p05, v3p06, v3p07, v3p08, v3p09, v3p10, v3p11, v3p12, v3p13, v3p14, v3p15, v3p16, v3p17, v3p18, v3p19, v3p20, v3p21, v3p22, v3p23, v3p24, v3p25, v3p26, v3p27, v3p28, v3p29, v3p30, v3p31, v3p32, v3p33, v3p34, v3p35, v3p36, v3p37, v3p38, v3p39, v3p40, v3p41, v3p42, v3p43, v3p44, v3p45, v3p46, v3p47, v3p48, v3p49, v3p50, v3p51, v3p52, v3p53, v3p54, v3p55, v3p56, v3p57, v3p58, v3p59_

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

_Skipped (Mode B missing or null): v3p01, v3p02, v3p03, v3p04, v3p05, v3p06, v3p07, v3p08, v3p09, v3p10, v3p11, v3p12, v3p13, v3p14, v3p15, v3p16, v3p17, v3p18, v3p19, v3p20, v3p21, v3p22, v3p23, v3p24, v3p25, v3p26, v3p27, v3p28, v3p29, v3p30, v3p31, v3p32, v3p33, v3p34, v3p35, v3p36, v3p37, v3p38, v3p39, v3p40, v3p41, v3p42, v3p43, v3p44, v3p45, v3p46, v3p47, v3p48, v3p49, v3p50, v3p51, v3p52, v3p53, v3p54, v3p55, v3p56, v3p57, v3p58, v3p59_

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

| (rows=human) \ (cols=anti) | allow | downrank | reject |
|---|---|---|---|
| allow | 0 | 0 | 0 |
| downrank | 0 | 0 | 0 |
| reject | 0 | 0 | 0 |

_Skipped (retrieve defer on gold or pred): v3p01, v3p02, v3p03, v3p04, v3p05, v3p06, v3p07, v3p08, v3p09, v3p10, v3p11, v3p12, v3p13, v3p14, v3p15, v3p16, v3p17, v3p18, v3p19, v3p20, v3p21, v3p22, v3p23, v3p24, v3p25, v3p26, v3p27, v3p28, v3p29, v3p30, v3p31, v3p32, v3p33, v3p34, v3p35, v3p36, v3p37, v3p38, v3p39, v3p40, v3p41, v3p42, v3p43, v3p44, v3p45, v3p46, v3p47, v3p48, v3p49, v3p50, v3p51, v3p52, v3p53, v3p54, v3p55, v3p56, v3p57, v3p58, v3p59_

### `mention_permission`

n=0; accuracy=n/a; macro-F1=n/a; κ_w²=n/a; off-by-one=n/a

| (rows=human) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 0 | 0 |
| deny | 0 | 0 |

## Anti-GEO vs LLM

### `endorsement_permission`

n=59; accuracy=0.983; macro-F1=0.924; κ_w²=0.848; off-by-one=0.017

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 3 | 1 |
| deny | 0 | 55 |

### `parasitic`

n=43; accuracy=0.907; macro-F1=0.476; κ_w²=0.000; off-by-one=0.093

| (rows=llm) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 39 | 4 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 0 | 0 | 0 |

_Skipped (Mode B missing or null): v3p03, v3p06, v3p10, v3p11, v3p12, v3p15, v3p26, v3p27, v3p37, v3p39, v3p40, v3p41, v3p50, v3p51, v3p52, v3p54_

### `factual_permission`

n=59; accuracy=0.847; macro-F1=0.420; κ_w²=0.448; off-by-one=0.136

| (rows=llm) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 5 | 3 | 0 | 0 |
| attribute_only | 0 | 45 | 1 | 0 |
| require_corroboration | 0 | 4 | 0 | 0 |
| deny | 0 | 1 | 0 | 0 |

### `retrieve_permission`

n=51; accuracy=0.745; macro-F1=0.492; κ_w²=-0.015; off-by-one=0.255

| (rows=llm) \ (cols=anti) | allow | downrank | reject |
|---|---|---|---|
| allow | 37 | 7 | 0 |
| downrank | 6 | 1 | 0 |
| reject | 0 | 0 | 0 |

_Skipped (retrieve defer on gold or pred): v3p03, v3p06, v3p15, v3p37, v3p39, v3p40, v3p41, v3p48_

### `mention_permission`

n=59; accuracy=0.729; macro-F1=0.422; κ_w²=0.000; off-by-one=0.271

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 43 | 16 |
| deny | 0 | 0 |

