# Anti_GEO

Defenses against Generative Engine Optimization (GEO) — detecting and mitigating manipulative web content in AI search pipelines.

## Structure

| Path | Purpose |
|---|---|
| `src/anti_geo/` | Production-style URL analysis pipeline (fetch → score → decide) |
| `demo/` | Educational simulations and CLI tools |
| `geo-optimizer/` | Vendored [Princeton GEO](https://github.com/GEO-optim/GEO) codebase (attack/benchmark side) |
| `tests/` | Offline tests |

## Quick start

```bash
pip install -r requirements.txt

# Optional: bundled Chromium for bot-protected sites (LoopNet, Forbes, etc.)
# Or skip this if Google Chrome / Edge is already installed — auto-detected.
playwright install chromium

# Defense layer demos (offline)
python3 demo/defense_demo.py

# Real URL analysis (httpx first, auto-fallback to Chromium when blocked)
PYTHONPATH=src python3 demo/analyze_url.py --offline-demo
PYTHONPATH=src python3 demo/analyze_url.py https://example.com

# Force browser fetch: ANTI_GEO_FETCH=browser PYTHONPATH=src python3 demo/analyze_url.py URL

# Defended query pipeline with contestability + commercial disclosure
PYTHONPATH=src python3 demo/analyze_url.py --offline-demo --defended --query "what is the best project management tool for small teams"
PYTHONPATH=src python3 demo/analyze_url.py --defended --json --query "..." URL1 URL2

# Longitudinal audit harness (mock offline; Perplexity requires PERPLEXITY_API_KEY)
PYTHONPATH=src python3 demo/audit_harness.py --engine mock
PERPLEXITY_API_KEY=... PYTHONPATH=src python3 demo/audit_harness.py --engine perplexity
```

## Governance modules

| Module | Purpose |
|---|---|
| `commercial_policy.py` | Precision-first commercial tier policy (block / hedge / disclose) |
| `disclosure.py` | Answer-level commercial influence labels |
| `contestability.py` | Baseline vs defended passage provenance export |
| `audit/` | Longitudinal citation auditing (mock + Perplexity adapters) |

Commercial disclosure labels appear only for **high-tier** signals (`affiliate_disclosure`, `link_sponsored`, etc.) when the source materially contributes to the defended answer.

## Attribution

`geo-optimizer/` is based on [GEO-optim/GEO](https://github.com/GEO-optim/GEO) (Aggarwal et al., KDD 2024). This repository is an independent Anti-GEO research project.
