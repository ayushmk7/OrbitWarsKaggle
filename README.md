# Orbit Wars (Kaggle)

A competitive agent for the Kaggle **Orbit Wars** simulation competition: conquer planets
orbiting a sun in continuous 2D space, win by holding the most ships at turn 500.

The agent (`src/main.py`) is a heuristic that scores every (source planet → target) move,
allocates ships globally with multi-source coordination, defends, attacks, grabs comets, and
predicts orbiting-planet intercepts. It beats the builtin `starter` opponent ~92%. The next
lever is forward-simulation lookahead — see the roadmap.

## Docs

| Doc | What |
|-----|------|
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | The plan to LB 1000+ (Phase A infra ✅, Phase B simulator/lookahead, Phase D learning). Start here. |
| [`docs/STATUS.md`](docs/STATUS.md) | Live scorecard: current version, win-rates, known loss classes. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Agent decision pipeline + harness + file map. |
| [`docs/INFRA.md`](docs/INFRA.md) | How to benchmark, inspect a game, run tests, build & submit. |
| [`docs/rules.txt`](docs/rules.txt) | Canonical game rules reference. |
| [`docs/archive/`](docs/archive/) | Historical plans (superseded). |

## Quickstart

```bash
pip install "kaggle-environments>=1.28"

# Benchmark vs meaningful opponents (NOT random):
PYTHONPATH=src python -m benchmark --games 60 --workers 8 --opponents starter,baseline

# Inspect one game turn-by-turn:
PYTHONPATH=src python -m inspect_game --seed 5 --opponent starter

# Tests:
PYTHONPATH=src python -m pytest -q

# Build the submission tarball:
PYTHONPATH=src python -m build_submission
```

`src/` is canonical; always run with `PYTHONPATH=src` (see the sys.path note in `ARCHITECTURE.md`).
