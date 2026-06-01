# Solution A — Implemented

This documents the Solution A work from `IMPROVEMENT_PLAN.md`: improving the
existing rule-based candidate-scoring agent end to end. Canonical agent lives in
`src/` (`main.py`, `geometry.py`, `prediction.py`); the submission tarball is
built from those three files.

## Headline result

The real problem was never visible against `random` (the agent beats it ~99%).
Benchmarked against the competition's own `starter` agent and against the
previous version (self-play), the gap was stark — and the fix closes it.

| Matchup (24 fixed seeds, 2p) | **New (solution_a_v3)** | Old (previous submission) |
|------------------------------|-------------------------|---------------------------|
| vs `starter`                 | **79.2 %** (19-5)       | 20.8 % (5-19)             |
| self-play (new vs old)       | **91.7 %** (22-2)       | —                         |
| vs `random`                  | 95.8 % (23-1)           | 100 %                     |

Per-turn runtime peaks at ~80 ms (Kaggle limit is 1 s). 4-player games run to
completion with zero agent errors.

> The old agent beating `starter` only ~21 % of the time is exactly the LB-521
> story: it crushed random and lost to everyone competent.

## A harness bug that was hiding the truth

`python -m benchmark` / `evaluate` run from the repo root put the repo root on
`sys.path[0]`, which **shadowed `src/main.py` with the stale root `main.py`**
(an old version with a `fleet_ships` NameError). Early "baseline" numbers were
secretly measuring the broken root file. `src/benchmark.py` now forces its own
directory (`src/`) to the front of `sys.path` before `import main`. The three
copies (`src/`, `submission/`, root) were re-synced to the canonical `src/`.

## What changed (mapping to the plan)

All scoring/selection now happens **globally across every source** instead of
greedily per-source.

- **A1 Global priority queue** — `_global_allocate` groups candidates by target,
  walks targets in value order, and allocates source budgets top-down.
- **A2 Fleet-in-flight tracking** — `_pending_arrivals` subtracts my own ships
  already heading to a target so we stop double-sending.
- **A3 Coordinated attacks** — when no single source can take a target,
  `_global_allocate` pools ships from multiple sources. Hardened for the combat
  rule that fleets only combine if they arrive on the **same tick**: contributors
  are restricted to a `COORD_WINDOW`-turn arrival window and the requirement is
  inflated for production-during-travel; if it can't be met safely, no ships are
  wasted.
- **A4 Consolidation** — `_generate_consolidation_candidates` moves idle ships
  off low-value backline planets toward the frontline (low score so it never
  preempts real expansion/attacks).
- **A5 Comet capture** — comet targets are scored from `comets` path data via
  `_comet_remaining_life`; skipped if unreachable or near expiry.
- **A6 Economy-aware strategy** — `_compute_economy` + `_strategic_posture`
  weight expansion vs attack by production advantage / neutral availability.
- **A7 Minimum fleet for speed** — `geometry.min_ships_for_arrival` sizes up
  fleets to distant targets (> `SPEED_MIN_DISTANCE`) so they don't crawl.
- **A8 Orbit-intercept timing fix** — `prediction.sample_orbit_intercept` now
  takes `current_step` and predicts the target at absolute step
  `current_step + future_turn` (the game rotates by absolute step), comparing
  travel time against the offset from now.
- **A9 Early-game rush** — `_early_game_bonus` heavily weights grabbing
  high-production neutrals in the first `EARLY_RUSH_END` turns.
- **A10 Preemptive defense** — `_preemptive_threat_score` (nearby enemy economy)
  feeds positional value even before a fleet is launched.
- **A11 4-player awareness** — in FFA games the agent focus-fires the production
  leader and stops bullying the weakest player.
- **A12 Overcommit / enemy reinforcement** — `_enemy_reinforcement` penalises
  captures a fortified enemy can contest before our fleet lands; `_positional_value`
  rewards holding frontline planets.

The candidate/decision-trace contract is preserved (rollout tooling and the
existing trace fields still work); new score components are additive and recorded.

## Testing

```bash
# unit + contract tests (no kaggle env needed)
python -m pytest tests/ -q

# real-opponent benchmark (needs kaggle-environments>=1.28; provides orbit_wars)
PYTHONPATH=src python -m benchmark --games 24 --opponents starter,baseline,random
PYTHONPATH=src python -m benchmark --games 24 --mode 4p          # 4-player FFA
```

`baseline/` holds a frozen copy of the previous agent (self-contained
`agent_v1.py` + `geometry_v1.py` + `prediction_v1.py`) so self-play measures new
vs old without import collisions.

## Building / submitting

```bash
python -m build_submission        # -> submission.tar.gz (main+geometry+prediction)
kaggle competitions submit orbit-wars -f submission.tar.gz -m "solution A v3"
```

## Known residual (not addressed — out of plan scope)

The inherited endgame policy (reserve → ~1 after step 470) can over-commit and
lose ships in the final turns on unlucky maps; it cost the single `random` loss
(seed 11, a prod-1 boxed-in home). It does not affect the `starter`/self-play
results and is a candidate for future tuning.
