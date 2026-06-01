# Status

Live scorecard. Update after each benchmark / version bump.

## Current agent

- **Version:** `solution_a_v4_orbit_intercept_fix` (`src/main.py`)
- **Class:** greedy 1-ply heuristic — score every (source, target), allocate globally, emit moves.
- **Compute:** ~3.6 ms/turn of a ~1000 ms/turn Kaggle budget (≈0.4% used).

## Local benchmark (the real signal — NOT vs `random`)

| Opponent | Result | Notes |
|----------|--------|-------|
| `starter` (builtin sniper) | **92%** (55/60) | up from 82.5% after the orbit-intercept fix |
| `baseline` (frozen v1 self-play) | **100%** (30/30), margin +3167 | decisive vs pre-fix agent |
| gym `expander` / `aggressive` / `turtle` | 8/8 each | weak scripted sparring; low signal |
| Kaggle LB | mid-500s (pre-fix submission) | v4 not yet re-submitted |

Run: `PYTHONPATH=src python -m benchmark --games 60 --workers 8 --opponents starter,baseline,expander,aggressive,turtle`

## Shipped recently

- **Orbit-intercept off-by-one fix** (commit 8c8838a): env actual position at step S =
  `predict(initial, av, S-1)`. Aiming one step ahead made fleets slip past orbiting planets
  (2.6–2.8u miss vs 1.7u radius) → on all-orbiting maps we captured nothing and got eliminated
  by ~turn 170. This was the catastrophic LB-521 cluster. **82.5% → 92% vs starter.**
- **A2 dribble fix:** only skip a target whose in-flight ships already fully cover it; otherwise
  require one decisive launch (cross-turn fleets don't merge in combat).
- **Infra (commit cf43c35):** parallel benchmark (`--workers`), Wilson 95% CI, opponent gym,
  per-seed `inspect_game` CLI.

## Known loss classes (vs starter: seeds 5, 9, 22, 32, 37)

| Class | Seed | Mechanism | Status |
|-------|------|-----------|--------|
| Lead-then-collapse | 5 | Peak 25 planets @turn180, rolled to 6 by 270. Thin empire, no defense of the lead. | **Open** — greedy preemptive-defense floor tried (A13) and *regressed*; routed to Phase B lookahead. |
| Production race | 9 | Opponent grabs high-prod planets, out-produces; we plateau. | **Open** — Phase B. |
| Early hoarding | 32 | Sits on 1 planet / many ships early. | **Open** — Phase B. |

Finding: these are temporal/strategic and resist greedy 1-ply patching — the reason Phase B
(forward-sim lookahead) is the real lever. See `ROADMAP.md`.

## Next

1. Re-submit v4 to Kaggle (bank the elimination-cluster fix). _Blocked previously by a Kaggle API 500._
2. Build Phase B simulator + lookahead (`ROADMAP.md`).
