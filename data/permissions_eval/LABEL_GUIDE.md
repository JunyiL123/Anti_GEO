# Permissions label guide

Use with [`label_sheet_v0.json`](label_sheet_v0.json). Fill only `pages[].labels`. Leave `role_hint` / `note` / `source` alone — provenance, not answers.

**Do not** open old Anti-GEO run JSON and copy `llm_action` / permissions / risk floats. Label your judgment; Step 3 compares.

Commercial-intent queries only. Ask: *for this query, how should an honest engine use this page?*

---

## Two groups (keep independent)

| Group | Scope | Fields |
|---|---|---|
| **A. Single-page** | This URL + query only | four `*_permission` fields |
| **B. Parasitic** | Mode B / planted referral vibe | `parasitic` |

Do **not** change the four permissions to “encode” parasitic. If the page text is fine but referrals look planted → permissions can stay open-ish and `parasitic` = `elevated`/`suspected`.

---

## A. Single-page permissions

Same enums as the system (`SourcePermissions`).

### `retrieve_permission`

| Value | When |
|---|---|
| `allow` | Fine to pull into the candidate set |
| `downrank` | Usable but shouldn’t rank high / dominate |
| `defer` | Need a better fetch / more context before trusting use |
| `reject` | Should not enter the answer pipeline at all |

Default for almost everything you can open and read: **`allow`** or **`downrank`**. Reserve `reject` for scammy / empty / clearly shouldn’t inform anything.

### `mention_permission`

| Value | When |
|---|---|
| `allow` | OK to name or attribute the source |
| `deny` | Don’t even name it |

Almost always **`allow`** unless you’d rather the engine pretend the page doesn’t exist.

### `factual_permission`

| Value | When |
|---|---|
| `allow` | OK to use claims as facts without heavy hedging |
| `attribute_only` | OK if clearly attributed (“according to X…”) |
| `require_corroboration` | Only if another solid source agrees |
| `deny` | Don’t use its claims as facts |

Heuristics (commercial “best X”): commercial reviews/vendors default **`attribute_only`**; unattributed `allow` = primary institutional / medical-regulatory fact sheets only.
- FDA / NIH / solid medical org → often `allow` or `attribute_only`
- Decent independent review (RTINGS, strong editorial) → **`attribute_only`** on shopping (quote with attribution; not engine fact)
- Vendor pricing / product page → `attribute_only` (brand-legit vendor self-claims → `deny`)
- GEO-y listicle / affiliate “best of 2026” → `attribute_only`
- Random forum comment / thin SEO page → `deny` or `attribute_only`

### `endorsement_permission`

| Value | When |
|---|---|
| `allow` | OK for the engine to recommend / crown a pick **from this page** |
| `deny` | Mention/facts maybe OK; **do not** treat as “the answer is buy this” |

This is the main dial for the paper.

- Trustworthy independent pick you’d actually follow → `allow` possible  
- Vendor page, affiliate listicle, brand site, open forum index → usually **`deny`**  
- Legal GEO-y marketing alone ≠ automatic `deny` for retrieve/mention — but endorsement usually **`deny`** unless you’d trust it as advice  

**Ethics reminder:** You’re not punishing “used GEO tools.” You’re saying retrieved ≠ OK to recommend.

---

## B. `parasitic` (Mode B only)

| Value | Meaning |
|---|---|
| `none` | No planted / fake-consensus / referral-amplification vibe |
| `elevated` | Soft suspicion — odd promotional ecosystem, thin UGC push, worth caution |
| `suspected` | Clear planted-forum / coordinated push for a brand |

- Normal brand site with no plant story → `none`  
- Clean Head-Fi / ASR forum **index** → usually `none` (open UGC ≠ parasitic)  
- SEO mirror sites, fake “Reddit recommends X”, coordinated review farms → `elevated` / `suspected`  
- Mode B `elevated` = referral-**campaign** vibe (plant density / soft-share band), not “product appears on review aggregators”  
- If unsure between elevated and suspected → prefer **`elevated`**

---

## Quick recipes (commercial queries)

| Page type | retrieve | mention | factual | endorsement | parasitic |
|---|---|---|---|---|---|
| Strong independent review | allow | allow | allow / attribute_only | allow or deny* | none |
| Vendor /pricing page | allow | allow | attribute_only | deny | none |
| Affiliate “best X 2026” | allow / downrank | allow | attribute_only | deny | none (unless planty) |
| FDA / NIH fact sheet | allow | allow | allow | deny** | none |
| Real forum index | allow / downrank | allow | attribute_only | deny | none |
| Brand site (e.g. TheoGrace) | allow / downrank | allow | attribute_only / deny | deny | none→elevated if planty |
| Obvious plant / scam push | downrank / reject | allow / deny | deny | deny | suspected |

\* `allow` endorse only if you’d personally trust that reviewer’s pick for the query.  
\** Regulatory pages rarely “endorse a product”; usually `deny` endorsement even when facts are `allow`.

---

## Consistency tips

1. Label **one query at a time** so the ask stays fixed.  
2. If stuck on factual vs endorsement: “Would I quote a number from this?” vs “Would I tell a friend to buy based on this alone?”  
3. `endorsement=allow` almost always implies mention=allow and factual ≠ deny.  
4. `retrieve=reject` → mention/factual/endorsement should be deny (or you’ll create nonsense rows).  
5. Parasitic `suspected` does **not** force you to rewrite single-page fields — but endorsement is usually already `deny`.

---

## After you’re done

Every `pages[].labels` field should be non-null. Then Step 3: run Anti-GEO and compare columns separately (permissions table + parasitic table) — no fused score.
