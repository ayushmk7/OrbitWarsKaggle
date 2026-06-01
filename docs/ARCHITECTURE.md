# Architecture

How the agent and harness fit together. Game rules are in `rules.txt`; the plan is in
`ROADMAP.md`.

## Runtime agent (bundled into `submission.tar.gz`)

| File | Role |
|------|------|
| `src/main.py` | Kaggle entrypoint. `agent(obs)` → moves; `decide_with_trace(obs)` → moves + full decision trace. The greedy decision pipeline. |
| `src/geometry.py` | Pure math: `distance_xy`, `angle_to_xy`, `fleet_speed`, `turns_to_reach`, `segment_intersects_circle`, `shot_hits_sun`, `min_ships_for_arrival`. |
| `src/prediction.py` | Orbiting-planet position prediction + intercept sampling (`predict_orbit_position`, `sample_orbit_intercept`). |
| `src/simulator.py` | _(Phase B, not yet built)_ forward game model + lookahead search. |

`build_submission.py` tars exactly the files in `AGENT_FILES`. The runtime must not do network
calls, file writes, or need API keys.

## Decision pipeline (`decide_with_trace`)

```
obs
 └─ parse planets/fleets/comets, my/enemy/neutral split
 └─ _compute_economy        → production/ship balance, per-opponent, leader
 └─ _strategic_posture      → expand_weight / attack_weight (A6)
 └─ _pending_arrivals       → ships already in flight per target (A2)
 └─ DEFENSE first:
      _detect_incoming_threats → _generate_reinforce_candidates → _select_defense_candidates
      (reserves its ships before any offense)
 └─ OFFENSE pool: for every (my planet, target):
      expand | attack | comet candidate, scored by
        _score_candidate / _score_attack_candidate
      with orbit intercept (prediction), sun-block, speed-min (A7),
      enemy-reinforcement (A12), 4p focus-fire (A11), early-rush bonus (A9)
 └─ _global_allocate        → allocate offense by target priority, with
                              multi-source coordination (A1 + A3)
 └─ _generate_consolidation_candidates → _global_allocate (A4, leftover budget)
 └─ emit moves: defenses, then offense, then consolidation
```

Every candidate (selected or rejected) is recorded in `decision["candidates"]` with `score`,
`score_components`, `legal`, `rejection_reason` — this trace is what `inspect_game` and the
rollout JSONL surface, and what Phase B will turn into action-sets.

### Phase B integration contract (planned)

`decide_with_trace` body becomes `_greedy_decide` verbatim. The new wrapper runs greedy, then
(behind `USE_SIMULATOR`) feeds the greedy candidate list to `simulator.search_decision` as the
**action-set generator**, simulates each set, and overrides `chosen_moves` — recording a
`decision["sim"]` sub-trace. `greedy_full` is always a candidate set and the `try/except`
fallback, so search can only tie-or-beat greedy and the agent never crashes.

## Harness (not bundled)

| File | Role |
|------|------|
| `src/benchmark.py` | Win-rate vs opponents (2p/4p), parallel `--workers`, Wilson CI. The primary quality gate. |
| `src/inspect_game.py` | Single-seed turn-by-turn trajectory + decision/rejection dump. |
| `src/opponents.py` | Scripted gym opponents (aggressive / expander / turtle). |
| `src/generate_rollouts.py` | Full decision-trace JSONL (schema v2) per game. |
| `src/evaluate.py` | Aggregate rollout outcomes into a summary JSON. |
| `src/validate_rollout_smoke.py` | Validate rollout JSONL schema completeness. |
| `baseline/` | Frozen previous agent (renamed `*_v1` modules) for self-play. |

## Mirrors & the sys.path footgun

`src/` is canonical. `submission/` and any root copies are build mirrors — keep them synced.
Running tools from the repo root puts root on `sys.path[0]`, so `import main` can resolve a stale
root copy; `benchmark.py` force-inserts its own dir first. Always run with `PYTHONPATH=src`.
