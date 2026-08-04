# Adjudication review (disagreements only)

Source: `data/permissions_eval/label_sheet_v0_adjudication.json`
Pages needing adjudication: **16** / 42
Field disagreement counts: `{'endorsement_permission': 3, 'factual_permission': 12, 'retrieve_permission': 6, 'parasitic': 1}`

Fill `adjudicated` blanks. Pre-agreed fields already shown.

## p03 — rtings.com
- query: best mattress for back pain 2026
- url: https://www.rtings.com/mattress/reviews/best/back-pain
- role_hint: `clean_review_or_institutional`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission | allow | allow | allow |
| mention_permission | allow | allow | allow |
| factual_permission | attribute_only | attribute_only | attribute_only |
| endorsement_permission ** | deny | allow | ☐ |
| parasitic | none | none | none |

## p10 — vanicream.com
- query: best moisturizer for dry skin drugstore
- url: https://www.vanicream.com/product/vanicream-moisturizing-cream
- role_hint: `medical_or_product`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission | allow | allow | allow |
| mention_permission | allow | allow | allow |
| factual_permission ** | require_corroboration | attribute_only | ☐ |
| endorsement_permission | deny | deny | deny |
| parasitic | none | none | none |

## p16 — protonvpn.com
- query: best VPN 2026
- url: https://protonvpn.com/blog/no-logs-audit
- role_hint: `commercial_product`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission | allow | allow | allow |
| mention_permission | allow | allow | allow |
| factual_permission ** | require_corroboration | attribute_only | ☐ |
| endorsement_permission | deny | deny | deny |
| parasitic | none | none | none |

## p19 — 1password.com
- query: best password manager for small business
- url: https://1password.com/pricing/password-manager
- role_hint: `vendor_pricing`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission | allow | allow | allow |
| mention_permission | allow | allow | allow |
| factual_permission ** | require_corroboration | attribute_only | ☐ |
| endorsement_permission | deny | deny | deny |
| parasitic | none | none | none |

## p20 — bitwarden.com
- query: best password manager for small business
- url: https://bitwarden.com/pricing/business/
- role_hint: `vendor_pricing`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission | allow | allow | allow |
| mention_permission | allow | allow | allow |
| factual_permission ** | require_corroboration | attribute_only | ☐ |
| endorsement_permission | deny | deny | deny |
| parasitic | none | none | none |

## p21 — keepersecurity.com
- query: best password manager for small business
- url: https://www.keepersecurity.com/pricing/business-and-enterprise.html
- role_hint: `vendor_pricing`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission ** | downrank | allow | ☐ |
| mention_permission | allow | allow | allow |
| factual_permission ** | deny | attribute_only | ☐ |
| endorsement_permission | deny | deny | deny |
| parasitic | none | none | none |

## p22 — dashlane.com
- query: best password manager for small business
- url: https://www.dashlane.com/pricing
- role_hint: `vendor_pricing`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission ** | downrank | allow | ☐ |
| mention_permission | allow | allow | allow |
| factual_permission ** | require_corroboration | attribute_only | ☐ |
| endorsement_permission | deny | deny | deny |
| parasitic | none | none | none |

## p23 — blog.lastpass.com
- query: best password manager for small business
- url: https://blog.lastpass.com/posts/notice-of-recent-security-incident
- role_hint: `expert_listicle`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission | allow | allow | allow |
| mention_permission | allow | allow | allow |
| factual_permission ** | require_corroboration | attribute_only | ☐ |
| endorsement_permission | deny | deny | deny |
| parasitic | none | none | none |

## p25 — comparedge.com
- query: best password manager for small business
- url: https://comparedge.com/tools/bitwarden/pricing
- role_hint: `commercial_product`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission ** | allow | downrank | ☐ |
| mention_permission | allow | allow | allow |
| factual_permission ** | attribute_only | require_corroboration | ☐ |
| endorsement_permission | deny | deny | deny |
| parasitic | none | none | none |

## p27 — rtings.com
- query: best budget mechanical keyboard reddit
- url: https://www.rtings.com/keyboard/reviews/best/cheap-mechanical-keyboards
- role_hint: `reddit_intent_mix`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission | allow | allow | allow |
| mention_permission | allow | allow | allow |
| factual_permission | attribute_only | attribute_only | attribute_only |
| endorsement_permission ** | deny | allow | ☐ |
| parasitic | none | none | none |

## p28 — keychron.com
- query: best budget mechanical keyboard reddit
- url: https://www.keychron.com/products/keychron-c3-pro-qmk-via-wired-mechanical-keyboard
- role_hint: `reddit_intent_mix`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission ** | downrank | allow | ☐ |
| mention_permission | allow | allow | allow |
| factual_permission ** | require_corroboration | attribute_only | ☐ |
| endorsement_permission | deny | deny | deny |
| parasitic | none | none | none |

## p29 — rtings.com
- query: best budget mechanical keyboard reddit
- url: https://www.rtings.com/keyboard/tools/compare/royal-kludge-rk61-vs-aula-f99-f75/28440/48018
- role_hint: `reddit_intent_mix`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission | allow | allow | allow |
| mention_permission | allow | allow | allow |
| factual_permission | attribute_only | attribute_only | attribute_only |
| endorsement_permission ** | deny | allow | ☐ |
| parasitic | none | none | none |

## p38 — theograce.com
- query: is theograce a good brand?
- url: https://www.theograce.com/
- role_hint: `brand_site_or_review`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission | downrank | downrank | downrank |
| mention_permission | allow | allow | allow |
| factual_permission ** | require_corroboration | deny | ☐ |
| endorsement_permission | deny | deny | deny |
| parasitic | elevated | elevated | elevated |

## p40 — theograce.com
- query: is theograce a good brand?
- url: https://www.theograce.com/articles/return-policy
- role_hint: `brand_site_or_review`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission ** | downrank | allow | ☐ |
| mention_permission | allow | allow | allow |
| factual_permission ** | require_corroboration | attribute_only | ☐ |
| endorsement_permission | deny | deny | deny |
| parasitic | elevated | elevated | elevated |

## p41 — theograce.com
- query: is theograce a good brand?
- url: https://www.theograce.com/articles/warranty-conditions
- role_hint: `brand_site_or_review`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission ** | downrank | allow | ☐ |
| mention_permission | allow | allow | allow |
| factual_permission ** | require_corroboration | attribute_only | ☐ |
| endorsement_permission | deny | deny | deny |
| parasitic | elevated | elevated | elevated |

## p42 — scamadviser.com
- query: is theograce a good brand?
- url: https://www.scamadviser.com/check-website/theograce.com
- role_hint: `trust_checker`

| field | human | llm | adjudicated |
|---|---|---|---|
| retrieve_permission | allow | allow | allow |
| mention_permission | allow | allow | allow |
| factual_permission | require_corroboration | require_corroboration | require_corroboration |
| endorsement_permission | deny | deny | deny |
| parasitic ** | elevated | none | ☐ |

