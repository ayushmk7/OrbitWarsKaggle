# Status

Live scorecard. Update after each benchmark / version bump.

## Current agent

- **Version:** `solution_b_v1_lookahead` (`src/main.py` + `src/simulator.py`)
- **Class:** greedy generates candidate action-sets; a 1-ply forward-simulation
  search picks the set that simulates best. Greedy is always a candidate and the
  crash/timeout fallback, so search can only tie-or-beat greedy.
- **Compute:** ~12–24 ms/turn (budget-capped at 160 ms), vs a ~1000 ms/turn limit.
  `USE_SIMULATOR=False` reverts to pure greedy (`solution_a_v4`).

## Local benchmark (the real signal — NOT vs `random`)

| Opponent | Result | Notes |
|----------|--------|-------|
| **self-play vs greedy** | **62.5%** (10-6), margin +1033 | lookahead beats pure greedy head-to-head (Bnext: focus-fire opponent model, horizon 30, defensive set) |
| `starter` (builtin sniper) | **87.5%** (35/40) | identical to greedy on the same seeds (picks `greedy_full` vs the weak sniper) — no regression |
| `baseline` (frozen v1 self-play) | **100%** (40/40), margin +3267 | decisive vs pre-fix agent |
| gym `expander` / `aggressive` / `turtle` | ~8/8 | weak scripted sparring; low signal |
| Kaggle LB | mid-500s (pre-fix submission) | v4/v1-lookahead not yet re-submitted |

Lookahead **ties** greedy against the weak `starter` (the 6–12 turn horizon + weak
opponent model can't reveal downside there) but **wins 62.5% head-to-head** — the
signal that the tactical lookahead (avoiding doomed launches / overextension within
the horizon) helps against LB-grade opponents that play more like our own greedy.

Run: `PYTHONPATH=src python -m benchmark --games 60 --workers 8 --opponents starter,baseline,expander,aggressive,turtle`

## Shipped recently (Phase B)

- **Forward simulator** (`simulator.py`): bit-exact re-implementation of the env
  interpreter (verified tick-exact vs the real env on 8 seeds incl. 3 full
  499-turn games with comets; `swept_pair_hit` parity on 10k random inputs).
- **1-ply lookahead** wired behind `USE_SIMULATOR` with greedy fallback. Beats
  pure greedy 62.5% in self-play; no regression vs starter.

## Earlier

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

Finding (confirmed through Phase B-next): these resist shallow lookahead. We tried
a focus-fire opponent model, horizon 30, and a synthesised defensive-consolidation
action set — **still byte-identical losses** (search picks `greedy_full`). The
collapse is driven by mid-game (turn ~200–270) decisions, not the turn-100
expansion, and the evaluator correctly rewards the production expansion brings, so
per-turn 1-ply lookahead can't resolve a strategy-level over-expansion punished
100+ turns later. The three losses also pull in OPPOSITE directions (seed 5 wants
less expansion; 9/32 want more), so no single eval knob fixes them. Real levers: a
**learned evaluator (Phase D)** or far deeper search.

## Next

1. Re-submit to Kaggle (bank orbit fix + lookahead). _Blocked previously by a Kaggle API 500._
2. Phase B tuning to extract more from lookahead and attack the long-horizon losses:
   stronger opponent model (model the opponent with our own greedy generator),
   longer/adaptive horizon, evaluator weight tuning (esp. `W_VULN`), and richer
   action-sets (alternative targets, not only subsets of greedy's plan).
3. Phase D (learning) remains deferred — see `ROADMAP.md`.
