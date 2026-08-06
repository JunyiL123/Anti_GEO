# Permissions confusion matrices (Mode A forced)

Generated: `2026-08-06T05:29:57.626327+00:00`

- Adjudication: `data/permissions_eval/label_sheet_v3_adjudication.json`
- Anti-GEO: `data/permissions_eval/label_sheet_v3_anti_geo_mode_a_forced.json`
- Parasitic Mode-B exclusions (Anti-GEO CMs): `v3p03, v3p06, v3p08, v3p10, v3p11, v3p12, v3p13, v3p15, v3p22, v3p23, v3p25, v3p27, v3p34, v3p37, v3p39, v3p40, v3p41, v3p50, v3p51, v3p52, v3p54`

Five separate matrices per comparison (no fused score). `parasitic` is **3-class** (`none` / `elevated` / `suspected`), not boolean. `retrieve_permission` rows where gold or pred is `defer` are excluded (fetch gate, not scored as a use-rights class).

## Summary — Anti-GEO vs Adjudicated (primary)

| Field | n | Accuracy | Macro-F1 | Quad. weighted κ | Off-by-one |
|---|---:|---:|---:|---:|---:|
| `endorsement_permission` | 59 | 0.949 | 0.687 | 0.383 | 0.051 |
| `parasitic` | 38 | 0.868 | 0.310 | -0.063 | 0.105 |
| `factual_permission` | 59 | 0.695 | 0.389 | 0.456 | 0.305 |
| `retrieve_permission` | 45 | 0.689 | 0.468 | -0.050 | 0.311 |
| `mention_permission` | 59 | 0.644 | 0.392 | 0.000 | 0.356 |

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

n=59; accuracy=0.949; macro-F1=0.687; κ_w²=0.383; off-by-one=0.051

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 1 | 3 |
| deny | 0 | 55 |

### `parasitic`

n=38; accuracy=0.868; macro-F1=0.310; κ_w²=-0.063; off-by-one=0.105

| (rows=adjudicated) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 33 | 3 | 0 |
| elevated | 1 | 0 | 0 |
| suspected | 1 | 0 | 0 |

_Skipped (Mode B missing or null): v3p03, v3p06, v3p08, v3p10, v3p11, v3p12, v3p13, v3p15, v3p22, v3p23, v3p25, v3p27, v3p34, v3p37, v3p39, v3p40, v3p41, v3p50, v3p51, v3p52, v3p54_

### `factual_permission`

n=59; accuracy=0.695; macro-F1=0.389; κ_w²=0.456; off-by-one=0.305

| (rows=adjudicated) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 4 | 5 | 0 | 0 |
| attribute_only | 0 | 36 | 10 | 0 |
| require_corroboration | 0 | 2 | 1 | 0 |
| deny | 0 | 0 | 1 | 0 |

### `retrieve_permission`

n=45; accuracy=0.689; macro-F1=0.468; κ_w²=-0.050; off-by-one=0.311

| (rows=adjudicated) \ (cols=anti) | allow | downrank | reject |
|---|---|---|---|
| allow | 30 | 9 | 0 |
| downrank | 5 | 1 | 0 |
| reject | 0 | 0 | 0 |

_Skipped (retrieve defer on gold or pred): v3p03, v3p06, v3p08, v3p10, v3p11, v3p15, v3p22, v3p23, v3p25, v3p34, v3p37, v3p39, v3p40, v3p41_

### `mention_permission`

n=59; accuracy=0.644; macro-F1=0.392; κ_w²=0.000; off-by-one=0.356

| (rows=adjudicated) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 38 | 21 |
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

n=59; accuracy=0.949; macro-F1=0.687; κ_w²=0.383; off-by-one=0.051

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 1 | 3 |
| deny | 0 | 55 |

### `parasitic`

n=38; accuracy=0.895; macro-F1=0.315; κ_w²=-0.047; off-by-one=0.079

| (rows=llm) \ (cols=anti) | none | elevated | suspected |
|---|---|---|---|
| none | 34 | 3 | 0 |
| elevated | 0 | 0 | 0 |
| suspected | 1 | 0 | 0 |

_Skipped (Mode B missing or null): v3p03, v3p06, v3p08, v3p10, v3p11, v3p12, v3p13, v3p15, v3p22, v3p23, v3p25, v3p27, v3p34, v3p37, v3p39, v3p40, v3p41, v3p50, v3p51, v3p52, v3p54_

### `factual_permission`

n=59; accuracy=0.695; macro-F1=0.400; κ_w²=0.447; off-by-one=0.305

| (rows=llm) \ (cols=anti) | allow | attribute_only | require_corroboration | deny |
|---|---|---|---|---|
| allow | 4 | 4 | 0 | 0 |
| attribute_only | 0 | 36 | 10 | 0 |
| require_corroboration | 0 | 3 | 1 | 0 |
| deny | 0 | 0 | 1 | 0 |

### `retrieve_permission`

n=44; accuracy=0.682; macro-F1=0.465; κ_w²=-0.055; off-by-one=0.318

| (rows=llm) \ (cols=anti) | allow | downrank | reject |
|---|---|---|---|
| allow | 29 | 9 | 0 |
| downrank | 5 | 1 | 0 |
| reject | 0 | 0 | 0 |

_Skipped (retrieve defer on gold or pred): v3p03, v3p06, v3p08, v3p10, v3p11, v3p15, v3p22, v3p23, v3p25, v3p34, v3p37, v3p39, v3p40, v3p41, v3p48_

### `mention_permission`

n=59; accuracy=0.644; macro-F1=0.392; κ_w²=0.000; off-by-one=0.356

| (rows=llm) \ (cols=anti) | allow | deny |
|---|---|---|
| allow | 38 | 21 |
| deny | 0 | 0 |

