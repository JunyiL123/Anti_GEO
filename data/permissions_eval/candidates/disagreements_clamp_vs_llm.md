# Eval-loop disagreements (system vs draft) — triage only

Generated: `2026-08-05T08:04:37.519917+00:00`

- Anti-GEO: `data/permissions_eval/label_sheet_v0_anti_geo_mode_a_forced_clamp_20260803_no_defer_match.json`
- Draft / LLM labels: `data/permissions_eval/label_sheet_v0_adjudication.json`

**Not paper gold.** Use to prioritize human adjudication. Do not optimize F1 against these rows.

## Counts by field

| Field | n |
|---|---:|
| `retrieve_permission` | 9 |
| `mention_permission` | 0 |
| `factual_permission` | 13 |
| `endorsement_permission` | 0 |
| `parasitic` | 3 |

Total: **25**

## Rows

- `p01` / `factual_permission`: system=`require_corroboration` draft=`attribute_only` — https://www.sleepfoundation.org/best-mattress/best-mattress-for-back-pain
- `p03` / `factual_permission`: system=`allow` draft=`attribute_only` — https://www.rtings.com/mattress/reviews/best/back-pain
- `p09` / `retrieve_permission`: system=`downrank` draft=`allow` — https://www.the-independent.com/extras/indybest/us/best-drugstore-moisturizer-b2922374.html
- `p13` / `factual_permission`: system=`require_corroboration` draft=`attribute_only` — https://www.security.org/vpn/best/
- `p14` / `factual_permission`: system=`require_corroboration` draft=`attribute_only` — https://uk.pcmag.com/vpn/138/the-best-vpn-services
- `p15` / `retrieve_permission`: system=`reject` draft=`allow` — https://www.security.org/vpn/best/no-log/
- `p15` / `factual_permission`: system=`deny` draft=`attribute_only` — https://www.security.org/vpn/best/no-log/
- `p19` / `retrieve_permission`: system=`downrank` draft=`allow` — https://1password.com/pricing/password-manager
- `p21` / `parasitic`: system=`elevated` draft=`none` — https://www.keepersecurity.com/pricing/business-and-enterprise.html
- `p23` / `retrieve_permission`: system=`downrank` draft=`allow` — https://blog.lastpass.com/posts/notice-of-recent-security-incident
- `p23` / `parasitic`: system=`elevated` draft=`none` — https://blog.lastpass.com/posts/notice-of-recent-security-incident
- `p24` / `factual_permission`: system=`allow` draft=`attribute_only` — https://www.security.org/password-manager/dashlane/
- `p25` / `retrieve_permission`: system=`allow` draft=`downrank` — https://comparedge.com/tools/bitwarden/pricing
- `p26` / `factual_permission`: system=`attribute_only` draft=`require_corroboration` — https://redditrecs.com/gaming-keyboard/model/aula-f75/
- `p27` / `factual_permission`: system=`allow` draft=`attribute_only` — https://www.rtings.com/keyboard/reviews/best/cheap-mechanical-keyboards
- `p28` / `retrieve_permission`: system=`downrank` draft=`allow` — https://www.keychron.com/products/keychron-c3-pro-qmk-via-wired-mechanical-keyboard
- `p28` / `factual_permission`: system=`require_corroboration` draft=`attribute_only` — https://www.keychron.com/products/keychron-c3-pro-qmk-via-wired-mechanical-keyboard
- `p29` / `factual_permission`: system=`allow` draft=`attribute_only` — https://www.rtings.com/keyboard/tools/compare/royal-kludge-rk61-vs-aula-f99-f75/28440/48018
- `p33` / `retrieve_permission`: system=`allow` draft=`downrank` — https://www.headphonesty.com/2025/11/reddit-comments-most-recommended-headphones-complaints/
- `p33` / `factual_permission`: system=`allow` draft=`require_corroboration` — https://www.headphonesty.com/2025/11/reddit-comments-most-recommended-headphones-complaints/
- `p33` / `parasitic`: system=`none` draft=`elevated` — https://www.headphonesty.com/2025/11/reddit-comments-most-recommended-headphones-complaints/
- `p40` / `retrieve_permission`: system=`downrank` draft=`allow` — https://www.theograce.com/articles/return-policy
- `p40` / `factual_permission`: system=`require_corroboration` draft=`attribute_only` — https://www.theograce.com/articles/return-policy
- `p41` / `retrieve_permission`: system=`downrank` draft=`allow` — https://www.theograce.com/articles/warranty-conditions
- `p41` / `factual_permission`: system=`require_corroboration` draft=`attribute_only` — https://www.theograce.com/articles/warranty-conditions
