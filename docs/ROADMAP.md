# Roadmap: the path to LB 1000+

The single forward-looking plan. Current state and results live in `STATUS.md`;
how the code fits together is in `ARCHITECTURE.md`; tooling usage is in `INFRA.md`.

## Why we are mid-500s (and why tuning won't fix it)

The agent is a mature **greedy 1-ply heuristic**. It beats the builtin `starter` 92%, but the
Kaggle leaderboard ranks us against *other competitors' bots*, which are far stronger than
`starter`. Two facts set the strategy:

1. **We use ~0.4% of the per-turn compute budget.** Every competitive bot in this genre spends
   that budget on **forward-simulation lookahead**. That is the ceiling lever.
2. **The remaining losses are temporal.** Lead-then-collapse, losing the production race, and
   early hoarding are all multi-turn dynamics. We *tried* the principled greedy fix (wiring in
   preemptive defense) and it regressed — greedy 1-ply cannot see far enough. Lookahead can.

So: bank the cheap wins, then build the simulator.

---

## Phase A — Infra + quick wins  ✅ (mostly done)

- **A1 Parallel benchmark** ✅ — `--workers` multiprocessing fan-out; fixes the sequential OOM.
- **A2 Per-seed inspector** ✅ — `inspect_game.py` trajectory + decision dump.
- **A3 Statistical rigor** ✅ — Wilson 95% CI on win-rate in benchmark summaries.
- **A4 Opponent gym** ✅ — `opponents.py`: aggressive / expander / turtle. (Currently weak; a
  stretch goal is to make them genuinely challenging, or replace with the Phase-B agent.)
- **A5 Loss-class heuristic fixes** — attempted, regressed, **deferred to Phase B** (see above).

## Phase B — Forward simulator + lookahead search  ✅ (v1 shipped)

Greedy is the *action-set generator*; a 1-ply search over candidate action-sets simulates each
N turns and picks the best board. **Shipped in `solution_b_v1_lookahead`** — simulator is
bit-exact (fidelity-tested), lookahead beats pure greedy 62.5% in self-play, no regression vs
starter. `USE_SIMULATOR=False` reverts to greedy.

**What v1 does NOT yet do:** flip the long-horizon losses (seeds 5/9/32). A 6–12 turn horizon
can't see a ~90-turn collapse, and the nearest-affordable opponent model is too weak to punish
overextension in-rollout, so on those seeds search just picks `greedy_full`. The value v1 adds is
tactical (avoiding doomed launches within the horizon) — hence the self-play win but the
starter-tie.

### Phase B-next ✅ (done — and it revealed the ceiling)
Shipped: focus-fire opponent model (attacks the player's planets, not nearest-affordable),
horizon 6→30, and a synthesised `consolidate_defensive` action set. Self-play margin rose
(+920 → +1033) with no regression — so it's a real if modest improvement to general play.

**But it did NOT flip the long-horizon losses (seeds 5/9/32)** — search still picks `greedy_full`
there. This is the empirical ceiling of shallow per-turn 1-ply lookahead for this game:
- The collapse is driven by mid-game decisions (turn ~200–270), not the turn-100 expansion the
  search evaluates; a feasible horizon can't bridge that gap.
- The evaluator correctly rewards the production expansion brings, so expanding always wins the
  short rollout.
- The three losses pull in opposite directions (5 wants less expansion, 9/32 want more), so no
  single eval/posture knob fixes all three (also why the A13 greedy tweak regressed).

**Remaining levers (escalating cost):** much deeper search (a real tree/MCTS — likely needs the
hot loop in C/numpy to fit the time budget in Python), or a **learned board evaluator** that
encodes the strategic "thin empire = fragile" judgment rather than discovering it by rollout →
that is Phase D.

Original design notes (still the reference for the build):

> Ground truth verified in `kaggle_environments/envs/orbit_wars/orbit_wars.py`: real collision is
> `swept_pair_hit` (continuous swept-pair, **not** the static segment check the agent uses for
> blocking); orbit rotation uses the **absolute** step (confirms the off-by-one fix); production
> happens *before* movement/combat; combat = sum-by-owner, top vs second, strict `<0` flip.

**B1 `src/simulator.py` — `GameState` + `step`.** Parallel primitive arrays indexed by dense
slot (not namedtuples), cheap `clone()` sharing read-only arrays. `step(state, actions)` mirrors
the exact tick order: expire comets → (skip hidden spawns) → launch → production → movement with
`swept_pair_hit` → planet rotation / comet advance → combat. Copy `swept_pair_hit` and
`point_to_segment_distance` verbatim from the env for bit-level parity.

**B2 Board evaluator.** Weighted terms targeting known weaknesses: production advantage × horizon
(production race), ship material, planet count, **vulnerability penalty** (garrison that can't
survive an inbound fleet = phantom asset — the anti-collapse term), **overextension penalty**,
terminal override (use the real win condition at the horizon).

**B3 Search + opponent model.** `build_action_sets` converts `main.py`'s ranked candidates into
~10–24 distinct action-SETS — `do_nothing`, `greedy_full` (always present → can only tie-or-beat
greedy), `defend_only`, `expand_only`, `attack_only`, top-K single-target, `greedy_minus_riskiest`,
coordinated-attack — each unioned with forced defenses. Greedy nearest-affordable opponent model
inside rollouts. Iterative deepening governed by `obs.remainingOverageTime`, 0.8 safety margin,
hard fallback to greedy below a budget floor.

**B4 Backward-compatible integration.** Refactor the current `decide_with_trace` body →
`_greedy_decide` verbatim; new `decide_with_trace` runs greedy then (behind `USE_SIMULATOR`)
`simulator.search_decision`, overrides `chosen_moves`, records a `decision["sim"]` sub-trace.
`try/except` → never crashes; greedy is always the fallback. Add `simulator.py` to `AGENT_FILES`.

**B5 Validation (non-negotiable).** Fidelity replay: drive the real env, replay actions through
the simulator, assert per-tick owner/ships equal and x/y within 1e-6 across seeds 1–20, 2p + 4p
(comet spawns hidden → validate the pre-spawn prefix, inject real spawns after). Per-phase unit
tests; property-test our `swept_pair_hit` vs the env's on 10k random inputs. Evaluator regression
guards. **Benchmark gate:** lookahead beats frozen greedy self-play >55–60%; no regression vs
starter (≥92%); seeds 5/9/32 fixed; per-turn P99 < 800 ms.

**Build order:** GameState → step (no comets, validate on steps 0–49) → comets → evaluator →
opponent+rollout+fixed-horizon → time budget + deepening + top-K. Each green before the next.

## Phase C — Docs  ✅

This doc set (ROADMAP / ARCHITECTURE / STATUS / INFRA) replaced the stale plans; old plans moved
to `docs/archive/`.

## Phase D — Learning loop (deferred, speced)

Keep DPO/ML deferred until the rule+search engine plateaus **and** Kaggle replays show *ranking*
mistakes (a correct move generated but ranked below a worse one), not missing logic. Trigger:
rollout tracing reliable + version-comparison benchmark + replay failures that are ranking errors.
No `dpo_*.py` until then. The Kaggle runtime must never need API keys or network calls.

---

## Footguns (learned the hard way)

- **Orbit timing:** env actual position at step S = `predict(initial, av, S-1)`. Aim at
  `current_step + future_turn - 1`. See `prediction.sample_orbit_intercept`.
- **Combat merging:** fleets launched on different turns arrive on different ticks and do NOT
  combine. Never dribble partial top-ups; send one decisive fleet.
- **sys.path shadowing:** running from repo root puts root on `sys.path[0]` and `import main`
  resolves the stale root copy. `src/` is canonical; benchmark force-inserts its own dir first.
- **Collision model:** the agent's `_first_blocking_distance` is a static ray check; the env uses
  continuous `swept_pair_hit`. The simulator must use the latter.
