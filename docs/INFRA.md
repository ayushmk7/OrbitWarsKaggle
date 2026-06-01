# Infra: how to run things

Always run with `PYTHONPATH=src` (the sys.path footgun — see `ARCHITECTURE.md`). The
`kaggle_environments` package ships the `orbit_wars` env and the `random`/`starter` opponents;
install with `pip install "kaggle-environments>=1.28"`.

## Benchmark (the quality gate)

Win-rate vs meaningful opponents — **NOT `random`** (we beat random trivially; it's no signal).

```bash
# Parallel, with confidence intervals and the full opponent set:
PYTHONPATH=src python -m benchmark --games 60 --workers 8 \
  --opponents starter,baseline,expander,aggressive,turtle --summary results/bench.json

# 4-player free-for-all:
PYTHONPATH=src python -m benchmark --games 20 --mode 4p --opponents starter
```

- `--workers N` fans games over a multiprocessing Pool (fixes the sequential OOM past ~60 games).
- Output: `vs <opp> [2p] W.. L.. T.. win_rate=0.92 (95% CI 0.82-0.97) avg_margin=+1199 (s)`.
- Opponents: `starter`, `random`, `baseline` (frozen v1 self-play), gym (`aggressive`, `expander`,
  `turtle`), and `main`/`self`.

## Inspect a single game

Answers "what went wrong in THIS game" — the lead-collapse / hoarding / missed-expansion patterns.

```bash
PYTHONPATH=src python -m inspect_game --seed 5 --opponent starter --every 15
PYTHONPATH=src python -m inspect_game --seed 18 --opponent starter --decisions-at 30
```

Prints the per-player economy trajectory (planets, production, ships), the final result, and —
with `--decisions-at` — our chosen moves plus the candidate-rejection breakdown at that step.

## Rollouts & evaluation

```bash
PYTHONPATH=src python -m generate_rollouts --start-seed 1 --games 20 \
  --output-dir data/rollouts --summary results/rollouts.json
PYTHONPATH=src python -m validate_rollout_smoke data/rollouts/<agent>/seed_0001.jsonl
```

Rollout JSONL is schema v2: a `metadata` record then one `step` record per turn, each carrying
`agent_decisions` with the full candidate list (`score`, `score_components`, `legal`,
`rejection_reason`, `chosen_moves`). This is the audit trail for any decision.

## Tests

```bash
PYTHONPATH=src python -m pytest -q     # 64 passing
```

Covered: geometry, prediction/intercept, main decision logic, rollout generation/schema,
evaluation aggregation. _(Phase B adds simulator fidelity + evaluator tests.)_

## Build & submit

```bash
PYTHONPATH=src python -m build_submission        # writes ./submission.tar.gz from src/
tar -tzf submission.tar.gz                       # should list only AGENT_FILES
kaggle competitions submit orbit-wars -f submission.tar.gz -m "solution_a_v4_orbit_intercept_fix"
kaggle competitions submissions orbit-wars
kaggle competitions leaderboard orbit-wars -s
```

After a submission, pull replays/logs for the feedback loop:

```bash
kaggle competitions episodes <SUBMISSION_ID> -v
kaggle competitions replay <EPISODE_ID> -p ./replays
kaggle competitions logs <EPISODE_ID> 0 -p ./logs
```

Keep `submission/` and any root mirrors synced to `src/` after changing the agent.
