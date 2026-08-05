# Eval-loop disagreements (system vs draft) — triage only

Generated: `2026-08-05T09:07:02.470397+00:00`

- Anti-GEO: `data/permissions_eval/label_sheet_v2_anti_geo_mode_a_forced.json`
- Draft / LLM labels: `data/permissions_eval/label_sheet_v2_llm_gold_draft.json`

**Not paper gold.** Use to prioritize human adjudication. Do not optimize F1 against these rows.

## Counts by field

| Field | n |
|---|---:|
| `retrieve_permission` | 29 |
| `mention_permission` | 14 |
| `factual_permission` | 27 |
| `endorsement_permission` | 1 |
| `parasitic` | 3 |

Total: **74**

## Rows

- `v2p01` / `retrieve_permission`: system=`reject` draft=`allow` — https://nucific.com/bio-x4/
- `v2p01` / `factual_permission`: system=`deny` draft=`attribute_only` — https://nucific.com/bio-x4/
- `v2p02` / `retrieve_permission`: system=`downrank` draft=`allow` — https://www.cochrane.org/evidence/CD008650_green-tea-weight-loss-and-weight-maintenance-overweight-or-obese-adults
- `v2p03` / `retrieve_permission`: system=`downrank` draft=`defer` — https://pubmed.ncbi.nlm.nih.gov/34758791/
- `v2p03` / `factual_permission`: system=`attribute_only` draft=`require_corroboration` — https://pubmed.ncbi.nlm.nih.gov/34758791/
- `v2p05` / `factual_permission`: system=`allow` draft=`attribute_only` — https://www.bbb.org/us/ca/westlake-village/profile/vitamins-and-supplements/nucific-1236-92054405
- `v2p06` / `retrieve_permission`: system=`allow` draft=`downrank` — https://www.reddit.com/r/Invisalign/comments/1uhzxjm/invisalign_vs_other_vendors/?utm_source=openai
- `v2p07` / `retrieve_permission`: system=`allow` draft=`defer` — https://www.reddit.com/r/Invisalign/comments/1uwhqam/best_affordable_clear_aligner/?utm_source=openai
- `v2p08` / `mention_permission`: system=`deny` draft=`allow` — https://www.reddit.com/r/orthodontics/comments/1iel1ip?utm_source=openai
- `v2p08` / `factual_permission`: system=`deny` draft=`require_corroboration` — https://www.reddit.com/r/orthodontics/comments/1iel1ip?utm_source=openai
- `v2p10` / `retrieve_permission`: system=`defer` draft=`downrank` — https://www.scamadviser.com/check-website/theograce.com?utm_source=openai
- `v2p10` / `mention_permission`: system=`deny` draft=`allow` — https://www.scamadviser.com/check-website/theograce.com?utm_source=openai
- `v2p10` / `factual_permission`: system=`deny` draft=`require_corroboration` — https://www.scamadviser.com/check-website/theograce.com?utm_source=openai
- `v2p11` / `retrieve_permission`: system=`defer` draft=`downrank` — https://www.trustpilot.com/review/theograce.com?utm_source=openai
- `v2p11` / `mention_permission`: system=`deny` draft=`allow` — https://www.trustpilot.com/review/theograce.com?utm_source=openai
- `v2p11` / `factual_permission`: system=`deny` draft=`require_corroboration` — https://www.trustpilot.com/review/theograce.com?utm_source=openai
- `v2p12` / `retrieve_permission`: system=`downrank` draft=`allow` — https://www.theograce.com/articles/warranty-conditions?utm_source=openai
- `v2p12` / `factual_permission`: system=`deny` draft=`attribute_only` — https://www.theograce.com/articles/warranty-conditions?utm_source=openai
- `v2p12` / `parasitic`: system=`elevated` draft=`none` — https://www.theograce.com/articles/warranty-conditions?utm_source=openai
- `v2p13` / `retrieve_permission`: system=`allow` draft=`downrank` — https://www.reddit.com/r/jewelry/comments/1rsr2s6/reviewing_my_terrible_experience_with_theo_grace/?utm_source=openai
- `v2p14` / `factual_permission`: system=`deny` draft=`attribute_only` — https://www.theograce.com/articles/product-and-general-info?utm_source=openai
- `v2p14` / `parasitic`: system=`elevated` draft=`none` — https://www.theograce.com/articles/product-and-general-info?utm_source=openai
- `v2p15` / `retrieve_permission`: system=`allow` draft=`defer` — https://pubmed.ncbi.nlm.nih.gov/40335666/?utm_source=openai
- `v2p15` / `factual_permission`: system=`attribute_only` draft=`require_corroboration` — https://pubmed.ncbi.nlm.nih.gov/40335666/?utm_source=openai
- `v2p16` / `retrieve_permission`: system=`allow` draft=`defer` — https://pubmed.ncbi.nlm.nih.gov/40314930/?utm_source=openai
- `v2p16` / `factual_permission`: system=`attribute_only` draft=`require_corroboration` — https://pubmed.ncbi.nlm.nih.gov/40314930/?utm_source=openai
- `v2p17` / `retrieve_permission`: system=`downrank` draft=`defer` — https://pubmed.ncbi.nlm.nih.gov/39070254/?utm_source=openai
- `v2p17` / `factual_permission`: system=`attribute_only` draft=`require_corroboration` — https://pubmed.ncbi.nlm.nih.gov/39070254/?utm_source=openai
- `v2p18` / `factual_permission`: system=`attribute_only` draft=`allow` — https://aasm.org/late-afternoon-and-early-evening-caffeine-can-disrupt-sleep-at-night/?utm_source=openai
- `v2p19` / `retrieve_permission`: system=`reject` draft=`allow` — https://www.fda.gov/consumers/consumer-updates/spilling-beans-how-much-caffeine-too-much?utm_source=openai
- `v2p19` / `mention_permission`: system=`deny` draft=`allow` — https://www.fda.gov/consumers/consumer-updates/spilling-beans-how-much-caffeine-too-much?utm_source=openai
- `v2p19` / `factual_permission`: system=`deny` draft=`allow` — https://www.fda.gov/consumers/consumer-updates/spilling-beans-how-much-caffeine-too-much?utm_source=openai
- `v2p20` / `mention_permission`: system=`deny` draft=`allow` — https://www.reddit.com/r/AskReddit/comments/1huspeu?utm_source=openai
- `v2p20` / `factual_permission`: system=`deny` draft=`attribute_only` — https://www.reddit.com/r/AskReddit/comments/1huspeu?utm_source=openai
- `v2p22` / `retrieve_permission`: system=`allow` draft=`defer` — https://pubmed.ncbi.nlm.nih.gov/37608660/?utm_source=openai
- `v2p23` / `retrieve_permission`: system=`reject` draft=`allow` — https://www.fda.gov/consumers/consumer-updates/fda-101-dietary-supplements?utm_source=openai
- `v2p23` / `mention_permission`: system=`deny` draft=`allow` — https://www.fda.gov/consumers/consumer-updates/fda-101-dietary-supplements?utm_source=openai
- `v2p23` / `factual_permission`: system=`deny` draft=`allow` — https://www.fda.gov/consumers/consumer-updates/fda-101-dietary-supplements?utm_source=openai
- `v2p25` / `retrieve_permission`: system=`defer` draft=`downrank` — https://support.nanoleaf.me/hc/en-us/articles/41533132708372-Wellness-Devices-Clearance-and-Certification?utm_source=openai
- `v2p25` / `mention_permission`: system=`deny` draft=`allow` — https://support.nanoleaf.me/hc/en-us/articles/41533132708372-Wellness-Devices-Clearance-and-Certification?utm_source=openai
- `v2p25` / `factual_permission`: system=`deny` draft=`attribute_only` — https://support.nanoleaf.me/hc/en-us/articles/41533132708372-Wellness-Devices-Clearance-and-Certification?utm_source=openai
- `v2p26` / `endorsement_permission`: system=`allow` draft=`deny` — https://time.com/7071807/do-at-home-red-light-masks-really-work/
- `v2p33` / `retrieve_permission`: system=`allow` draft=`downrank` — https://www.grammarly.com/ai-writing-assistant?msockid=360d0f102f15652c0ab919712e0a6493&utm_source=openai
- `v2p34` / `retrieve_permission`: system=`downrank` draft=`allow` — https://guides.turnitin.com/hc/en-us/articles/27139000787853-How-should-I-review-the-AI-Writing-report?utm_source=openai
- `v2p34` / `factual_permission`: system=`attribute_only` draft=`allow` — https://guides.turnitin.com/hc/en-us/articles/27139000787853-How-should-I-review-the-AI-Writing-report?utm_source=openai
- `v2p35` / `retrieve_permission`: system=`allow` draft=`defer` — https://www.reddit.com/r/StandingDesk/comments/1reechm/flexispot_promo_code/?utm_source=openai
- `v2p35` / `factual_permission`: system=`attribute_only` draft=`require_corroboration` — https://www.reddit.com/r/StandingDesk/comments/1reechm/flexispot_promo_code/?utm_source=openai
- `v2p35` / `parasitic`: system=`none` draft=`elevated` — https://www.reddit.com/r/StandingDesk/comments/1reechm/flexispot_promo_code/?utm_source=openai
- `v2p36` / `mention_permission`: system=`deny` draft=`allow` — https://www.reddit.com/r/FlexiSpot_Official/comments/1f13duj?utm_source=openai
- `v2p36` / `factual_permission`: system=`deny` draft=`require_corroboration` — https://www.reddit.com/r/FlexiSpot_Official/comments/1f13duj?utm_source=openai
- `v2p37` / `retrieve_permission`: system=`defer` draft=`allow` — https://www.flexispot.com/deals
- `v2p37` / `mention_permission`: system=`deny` draft=`allow` — https://www.flexispot.com/deals
- `v2p37` / `factual_permission`: system=`deny` draft=`attribute_only` — https://www.flexispot.com/deals
- `v2p38` / `mention_permission`: system=`deny` draft=`allow` — https://law.justia.com/cases/federal/district-courts/california/candce/5%3A2024cv09470/441974/277/
- `v2p38` / `factual_permission`: system=`deny` draft=`attribute_only` — https://law.justia.com/cases/federal/district-courts/california/candce/5%3A2024cv09470/441974/277/
- `v2p39` / `retrieve_permission`: system=`defer` draft=`allow` — https://chromewebstore.google.com/detail/honey-automated-coupons-r/bmnlcjabgnpnenekpadlanbbkooimhnj?hl=en-US
- `v2p39` / `mention_permission`: system=`deny` draft=`allow` — https://chromewebstore.google.com/detail/honey-automated-coupons-r/bmnlcjabgnpnenekpadlanbbkooimhnj?hl=en-US
- `v2p39` / `factual_permission`: system=`deny` draft=`attribute_only` — https://chromewebstore.google.com/detail/honey-automated-coupons-r/bmnlcjabgnpnenekpadlanbbkooimhnj?hl=en-US
- `v2p41` / `factual_permission`: system=`attribute_only` draft=`allow` — https://developer.chrome.com/blog/cws-policy-update-affiliate-ads-2025?hl=en
- `v2p43` / `retrieve_permission`: system=`downrank` draft=`allow` — https://mullvad.net/en/help/no-logging-data-policy?next=%2Fen%2Faccount%2Fdevices&utm_source=openai
- `v2p45` / `retrieve_permission`: system=`downrank` draft=`allow` — https://ringconn.com/pages/ringconn-gen-2-air
- `v2p47` / `retrieve_permission`: system=`allow` draft=`downrank` — https://www.reddit.com/r/SmartRings/comments/1v30qf5/oura_or_ringconn/
- `v2p49` / `retrieve_permission`: system=`allow` draft=`downrank` — https://www.reddit.com/r/erectiledysfunction/comments/1t2koht/which_ed_med_worked_better_for_you/?utm_source=openai
- `v2p50` / `factual_permission`: system=`attribute_only` draft=`allow` — https://www.auanet.org/guidelines-and-quality/guidelines/erectile-dysfunction-%28ed%29-guideline?source=post_page---------------------------&utm_source=openai
- `v2p51` / `retrieve_permission`: system=`defer` draft=`allow` — https://www.mayoclinic.org/diseases-conditions/erectile-dysfunction/in-depth/erectile-dysfunction-herbs/art-20044394?p=1&utm_source=openai
- `v2p51` / `mention_permission`: system=`deny` draft=`allow` — https://www.mayoclinic.org/diseases-conditions/erectile-dysfunction/in-depth/erectile-dysfunction-herbs/art-20044394?p=1&utm_source=openai
- `v2p51` / `factual_permission`: system=`deny` draft=`allow` — https://www.mayoclinic.org/diseases-conditions/erectile-dysfunction/in-depth/erectile-dysfunction-herbs/art-20044394?p=1&utm_source=openai
- `v2p53` / `retrieve_permission`: system=`defer` draft=`allow` — https://www.mayoclinic.org/diseases-conditions/erectile-dysfunction/diagnosis-treatment/drc-20355782?utm_source=openai
- `v2p53` / `mention_permission`: system=`deny` draft=`allow` — https://www.mayoclinic.org/diseases-conditions/erectile-dysfunction/diagnosis-treatment/drc-20355782?utm_source=openai
- `v2p53` / `factual_permission`: system=`deny` draft=`allow` — https://www.mayoclinic.org/diseases-conditions/erectile-dysfunction/diagnosis-treatment/drc-20355782?utm_source=openai
- `v2p55` / `retrieve_permission`: system=`defer` draft=`allow` — https://www.optimumnutrition.com/en-us/products/gold-standard-100-whey-protein-powder?bvstate=pg%3A41%2Fct%3Ar&code=BUYMORE&gclsrc=aw.ds
- `v2p55` / `mention_permission`: system=`deny` draft=`allow` — https://www.optimumnutrition.com/en-us/products/gold-standard-100-whey-protein-powder?bvstate=pg%3A41%2Fct%3Ar&code=BUYMORE&gclsrc=aw.ds
- `v2p55` / `factual_permission`: system=`deny` draft=`attribute_only` — https://www.optimumnutrition.com/en-us/products/gold-standard-100-whey-protein-powder?bvstate=pg%3A41%2Fct%3Ar&code=BUYMORE&gclsrc=aw.ds
- `v2p57` / `retrieve_permission`: system=`downrank` draft=`allow` — https://www.ozempic.com/savings-and-resources/save-on-ozempic.html
