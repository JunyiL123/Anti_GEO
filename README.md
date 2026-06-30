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

# Defense layer demos (offline)
python3 demo/defense_demo.py

# Real URL analysis
PYTHONPATH=src python3 demo/analyze_url.py --offline-demo
PYTHONPATH=src python3 demo/analyze_url.py https://example.com
```

## Attribution

`geo-optimizer/` is based on [GEO-optim/GEO](https://github.com/GEO-optim/GEO) (Aggarwal et al., KDD 2024). This repository is an independent Anti-GEO research project.
