# Label sheet v1 — what to open

**Label this file only:**
`data/permissions_eval/label_sheet_v1.json`

- 20 commercial queries, 112 engine cites
- Fill `pages[].labels` (human). Independent LLM labels live in `pages[].llm_labels`
- Follow `data/permissions_eval/LABEL_GUIDE.md`
- No Anti-GEO permissions / parasitic predictions in this file

**Adjudicate human vs LLM disagreements here:**
- Review: `data/permissions_eval/label_sheet_v1_adjudication.md` (disagreements only; fill ☐)
- Canonical: `data/permissions_eval/label_sheet_v1_adjudication.json` → set each `null` in `adjudicated_labels`
- Only dual-labeled pages are included; regenerate after more human labels land

**Do not open while labeling (system side):**
- `label_sheet_v1_anti_geo_mode_a_forced.json` (written by background Anti-GEO)
- `label_sheet_v1_cite_raw.json` (raw cite lists only — optional debug)

Anti-GEO can run in parallel on the same URLs (forced cites).
