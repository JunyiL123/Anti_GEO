# Adjudication review (disagreements only) — v1

Source: `data/permissions_eval/label_sheet_v1_adjudication.json`
Pages needing adjudication: **8** / 47 dual-labeled (source sheet has 112 pages; 65 still missing human labels)
Field disagreement counts: `{'endorsement_permission': 5, 'factual_permission': 2, 'retrieve_permission': 1}`

Fill `adjudicated` blanks (☐ → one of the enum values). Pre-agreed fields already shown.
Also fill the matching `null` in `adjudicated_labels` in the JSON (canonical for eval).

Allowed values:

- `retrieve_permission`: allow | downrank | defer | reject
- `mention_permission`: allow | deny
- `factual_permission`: allow | attribute_only | require_corroboration | deny
- `endorsement_permission`: allow | deny
- `parasitic`: none | elevated | suspected



## v1p04 — [solereview.com](http://solereview.com)

- query: best running shoes for flat feet 2026
- url: [https://www.solereview.com/best-running-shoes-for-overpronators/](https://www.solereview.com/best-running-shoes-for-overpronators/)
- llm notes: Sole Review is long-running independent shoe review (buys shoes, publishes receipts) with affiliate links. Trustworthy enough to allow endorsement for overpronation/stability picks.


| field                     | human          | llm            | adjudicated    |
| ------------------------- | -------------- | -------------- | -------------- |
| retrieve_permission       | allow          | allow          | allow          |
| mention_permission        | allow          | allow          | allow          |
| factual_permission        | attribute_only | attribute_only | attribute_only |
| endorsement_permission ** | deny           | allow          | deny           |
| parasitic                 | none           | none           | none           |


*Your final decision (optional free text):*

```
adjudicator_note[v1p04]: 
```



## v1p10 — [downloads.energystar.gov](http://downloads.energystar.gov)

- query: best air purifier for allergies
- url: [https://downloads.energystar.gov/bi/qplist/Room_Air_Cleaners_Qualified_Product_List.pdf?bae4-e90d=&utm_source=openai](https://downloads.energystar.gov/bi/qplist/Room_Air_Cleaners_Qualified_Product_List.pdf?bae4-e90d=&utm_source=openai)
- llm notes: ENERGY STAR qualified room air cleaners PDF list. Use for certification/efficiency facts; does not pick a single best allergy purifier.


| field                     | human | llm   | adjudicated |
| ------------------------- | ----- | ----- | ----------- |
| retrieve_permission       | allow | allow | allow       |
| mention_permission        | allow | allow | allow       |
| factual_permission        | allow | allow | allow       |
| endorsement_permission ** | allow | deny  | allow       |
| parasitic                 | none  | none  | none        |


*Your final decision (optional free text):*

```
adjudicator_note[v1p10]: 
```



## v1p11 — [popularmechanics.com](http://popularmechanics.com)

- query: best air purifier for allergies
- url: [https://www.popularmechanics.com/technology/gear/a71054072/coway-airmega-mighty2-air-purifier-review/?utm_source=openai](https://www.popularmechanics.com/technology/gear/a71054072/coway-airmega-mighty2-air-purifier-review/?utm_source=openai)
- llm notes: Popular Mechanics single-product Coway review — lifestyle/affiliate-leaning gear media. Attribute; require more before crowning for allergies.


| field                  | human                 | llm            | adjudicated    |
| ---------------------- | --------------------- | -------------- | -------------- |
| retrieve_permission    | allow                 | allow          | allow          |
| mention_permission     | allow                 | allow          | allow          |
| factual_permission **  | require_corroboration | attribute_only | attribute_only |
| endorsement_permission | deny                  | deny           | deny           |
| parasitic              | none                  | none           | none           |


*Your final decision (optional free text):*

```
adjudicator_note[v1p11]: 
```



## v1p14 — [asthmaandallergyfriendly.com](http://asthmaandallergyfriendly.com)

- query: best air purifier for allergies
- url: [https://asthmaandallergyfriendly.com/USA/certified_products/products_categories/air-cleaners/portable-air-cleaners/](https://asthmaandallergyfriendly.com/USA/certified_products/products_categories/air-cleaners/portable-air-cleaners/)
- llm notes: Asthma & Allergy Friendly certified portable air cleaners list (AAFA + Allergy Standards). Legitimate certification catalog — facts about certification OK; do not treat mark as crowning a best product.


| field                     | human | llm   | adjudicated |
| ------------------------- | ----- | ----- | ----------- |
| retrieve_permission       | allow | allow | allow       |
| mention_permission        | allow | allow | allow       |
| factual_permission        | allow | allow | allow       |
| endorsement_permission ** | allow | deny  | allow       |
| parasitic                 | none  | none  | none        |


*Your final decision (optional free text):*

```
adjudicator_note[v1p14]: 
```



## v1p15 — [forbes.com](http://forbes.com)

- query: best standing desk converter
- url: [https://www.forbes.com/sites/forbes-personal-shopper/article/best-standing-desk-converters/?utm_source=openai](https://www.forbes.com/sites/forbes-personal-shopper/article/best-standing-desk-converters/?utm_source=openai)
- llm notes: Forbes Personal Shopper 'best standing desk converters' is affiliate commerce roundup. Downrank vs stronger independent tests; deny endorsement.


| field                  | human          | llm            | adjudicated    |
| ---------------------- | -------------- | -------------- | -------------- |
| retrieve_permission ** | allow          | downrank       | downrank       |
| mention_permission     | allow          | allow          | allow          |
| factual_permission     | attribute_only | attribute_only | attribute_only |
| endorsement_permission | deny           | deny           | deny           |
| parasitic              | none           | none           | none           |


*Your final decision (optional free text):*

```
adjudicator_note[v1p15]: 
```



## v1p25 — [notebookcheck.net](http://notebookcheck.net)

- query: best portable monitor for travel
- url: [https://www.notebookcheck.net/14-inch-Dell-C1422H-portable-monitor-review-Lightweight-and-basic-with-no-extras.595270.0.html](https://www.notebookcheck.net/14-inch-Dell-C1422H-portable-monitor-review-Lightweight-and-basic-with-no-extras.595270.0.html)
- llm notes: Notebookcheck Dell C1422H portable monitor review — established laptop/display lab tester. Endorsement allow for that model.


| field                     | human          | llm            | adjudicated    |
| ------------------------- | -------------- | -------------- | -------------- |
| retrieve_permission       | allow          | allow          | allow          |
| mention_permission        | allow          | allow          | allow          |
| factual_permission        | attribute_only | attribute_only | attribute_only |
| endorsement_permission ** | deny           | allow          | deny           |
| parasitic                 | none           | none           | none           |


*Your final decision (optional free text):*

```
adjudicator_note[v1p25]: 
```



## v1p30 — [soundguys.com](http://soundguys.com)

- query: best noise cancelling earbuds vs AirPods Pro
- url: [https://www.soundguys.com/sennheiser-momentum-true-wireless-4-review-111429/](https://www.soundguys.com/sennheiser-momentum-true-wireless-4-review-111429/)
- llm notes: SoundGuys Sennheiser MTW4 review with measurements. Strong audio measurement site — endorsement allow.


| field                     | human          | llm            | adjudicated    |
| ------------------------- | -------------- | -------------- | -------------- |
| retrieve_permission       | allow          | allow          | allow          |
| mention_permission        | allow          | allow          | allow          |
| factual_permission        | attribute_only | attribute_only | attribute_only |
| endorsement_permission ** | deny           | allow          | deny           |
| parasitic                 | none           | none           | none           |


*Your final decision (optional free text):*

```
adjudicator_note[v1p30]: 
```



## v1p43 — [dailymed.nlm.nih.gov](http://dailymed.nlm.nih.gov)

- query: best sunscreen for oily skin drugstore
- url: [https://dailymed.nlm.nih.gov/dailymed/getFile.cfm?setid=e1310453-1880-43a5-982b-cf9b30cfdc47&type=pdf&utm_source=openai](https://dailymed.nlm.nih.gov/dailymed/getFile.cfm?setid=e1310453-1880-43a5-982b-cf9b30cfdc47&type=pdf&utm_source=openai)
- llm notes: DailyMed/NLM drug-label PDF for a sunscreen. Authoritative label facts (SPF, actives); not a 'best for oily skin' endorsement.


| field                  | human          | llm   | adjudicated |
| ---------------------- | -------------- | ----- | ----------- |
| retrieve_permission    | allow          | allow | allow       |
| mention_permission     | allow          | allow | allow       |
| factual_permission **  | attribute_only | allow | allow       |
| endorsement_permission | deny           | deny  | deny        |
| parasitic              | none           | none  | none        |


*Your final decision (optional free text):*

```
adjudicator_note[v1p43]: 
```

