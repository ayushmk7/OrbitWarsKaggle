# Orbit Wars: Implementation Tasks (Solution A)

All tasks address the 14 root causes from IMPROVEMENT_PLAN.md plus additional gaps discovered during analysis. Each task maps to specific root causes it fixes.

**Rule: Stop benchmarking against `random`. Every task must be validated against the starter agent and via self-play.**

---

## Phase 0: Testing Infrastructure (Prerequisite for Everything)

### Task 0.1: Add Starter Agent as Benchmark Opponent
**Fixes:** Root Cause — only tested against random
**Files:** `evaluate.py`
**Why first:** Every subsequent task needs a real opponent to validate against. Random gives zero signal.

- [ ] Copy competition starter agent (`orbit-wars-data/orbit-wars.zip/main.py`) to `opponents/nearest_sniper.py`
- [ ] Update `evaluate.py` to accept file paths as opponents (not just `"random"`)
- [ ] Run baseline benchmark: current agent vs `nearest_sniper` on 100 seeds
- [ ] Save results to `results/baseline_vs_nearest_sniper.json`
- [ ] Record win rate — this is the new baseline to beat

```bash
python evaluate.py --start-seed 1 --games 100 --opponents opponents/nearest_sniper.py \
  --summary results/baseline_vs_nearest_sniper.json
```

### Task 0.2: Add Self-Play Evaluation
**Fixes:** Root Cause — only tested against random
**Files:** `evaluate.py`

- [ ] Add `--self-play` flag to `evaluate.py` that runs current `main.py` vs a saved copy
- [ ] Before making changes, snapshot current agent to `opponents/v1_baseline.py`
- [ ] Self-play baseline: should be roughly 50/50 win rate (sanity check)

### Task 0.3: Add 4-Player Evaluation
**Fixes:** Root Cause #11 — no 4-player awareness
**Files:** `evaluate.py`

- [ ] Add `--players 4` flag to `evaluate.py`
- [ ] Run 4-player games with 4 copies of current agent
- [ ] Run 4-player games with current agent + 3 random opponents
- [ ] Save results separately (4p games have different dynamics)

### Task 0.4: Download and Analyze Kaggle Replays
**Fixes:** Root Cause — only tested against random
**Files:** new script `analyze_replays.py`

- [ ] Run `kaggle competitions submissions orbit-wars` to get submission IDs
- [ ] Download 5-10 replays from losses: `kaggle competitions replay <EPISODE_ID> -p ./replays`
- [ ] Download corresponding logs: `kaggle competitions logs <EPISODE_ID> 0 -p ./logs`
- [ ] Write `analyze_replays.py` that reads replay JSON and reports:
  - Turn of first enemy contact
  - Production totals at turns 50, 150, 300
  - Planet ownership timeline
  - Ship count timeline
  - Key turning points (when we fell behind)
- [ ] Document 3-5 specific failure patterns from real losses

---

## Phase 1: Early Game (Highest Impact)

### Task 1.1: Early-Game Rush Scoring
**Fixes:** Root Cause #9 — no early-game rush optimization
**Files:** `main.py`
**Impact:** +100-200 leaderboard positions (estimated)

- [ ] Add `_early_game_bonus(step, target, travel_turns)` function
  - Returns large bonus for high-production neutrals captured in first 30-50 turns
  - Formula: `max(0, 50 - step - travel_turns) * target.production * 5`
  - Returns 0 after step 50 or for non-neutral targets
- [ ] Integrate early bonus into `_score_candidate()` scoring
- [ ] Add to `score_components` trace for debugging
- [ ] Test: at turn 0, a production-5 neutral at distance 20 scores higher than production-2 at distance 5
- [ ] Benchmark vs nearest_sniper: expect win rate improvement

### Task 1.2: Send More Ships Early for Speed
**Fixes:** Root Cause #8 — small-fleet speed penalty ignored
**Files:** `main.py`, `geometry.py`

- [ ] Add `_min_ships_for_arrival(distance, max_turns)` to `geometry.py`
  - Binary search for minimum ships where `turns_to_reach(distance, ships) <= max_turns`
- [ ] In early game (step < 50), override `ships_needed` with `max(ships_needed, speed_minimum)`
  - `speed_minimum = _min_ships_for_arrival(distance, max_turns=15)`
  - Sending 30 ships instead of 6 to a distant neutral gets there 3x faster
- [ ] Test: fleet of 30 ships arrives before fleet of 6 ships at same distance
- [ ] Verify we don't drain source planet below reserve

### Task 1.3: Lower Early-Game Reserves
**Fixes:** Root Cause #10 — reserve policy tuned for random
**Files:** `main.py`

- [ ] Change early-game reserve from `max(3, production)` to `max(1, production // 2)`
  - In early game, every ship sitting idle is a lost neutral
  - Home planet production refills quickly
- [ ] Only apply aggressive reserves for first 30 turns, then ramp up
- [ ] Test: at step 5 with a production-3 planet, reserve should be 1 not 3
- [ ] Benchmark: should capture more neutrals in first 50 turns

---

## Phase 2: Resource Efficiency

### Task 2.1: Fleet-In-Flight Tracking
**Fixes:** Root Cause #2 — no fleet-in-flight tracking
**Files:** `main.py`
**Impact:** +50-100 leaderboard positions

- [ ] Add `_compute_pending_attacks(my_fleets, targets, planets)` function
  - For each of our fleets in flight, determine which target planet it's heading toward
  - Use `_first_blocking_distance()` (already exists) to match fleet to target
  - Return `dict[target_id -> total_ships_incoming]`
- [ ] In candidate generation, reduce `ships_needed` by already-incoming ships:
  ```python
  already_sent = pending.get(target.id, 0)
  adjusted_ships_needed = max(1, base_ships_needed - already_sent)
  ```
- [ ] Add `pending_ships_to_target` to candidate trace for debugging
- [ ] Skip targets entirely if `already_sent >= base_ships_needed`
- [ ] Test: if 20 ships already heading to a target with 15 garrison, don't send more
- [ ] Benchmark vs nearest_sniper

### Task 2.2: Global Priority Queue
**Fixes:** Root Cause #5 — greedy per-source, not global optimization
**Files:** `main.py`
**Impact:** +50-100 leaderboard positions

- [ ] Replace per-source `_select_budgeted_candidates()` with global `_select_global_candidates()`
- [ ] Collect ALL candidates from ALL sources into one list
- [ ] Sort globally by score descending
- [ ] Allocate top-down, deducting from per-source budgets as candidates are selected
- [ ] Keep `MAX_MOVES_PER_SOURCE` limit per source planet
- [ ] Rejection reason `"global_budget_exhausted"` when source runs out
- [ ] Test: high-score candidate from source B selected before low-score from source A
- [ ] Benchmark vs nearest_sniper: compare ship efficiency

### Task 2.3: Consolidation Moves
**Fixes:** Root Cause #3 — no consolidation
**Files:** `main.py`
**Impact:** +30-50 leaderboard positions

- [ ] Add `_identify_frontline(my_planets, enemy_planets)` function
  - Frontline = my planets within distance 30 of any enemy planet
  - Backline = my planets not near any enemy and not near any neutral
- [ ] Add `_generate_consolidation_candidates(my_planets, enemy_planets, step)`
  - Source: backline planets with ships > 10
  - Target: frontline or high-production friendly planets
  - Ships to send: `source.ships - max(2, source.production)`
  - Score: `ships_to_send * 0.5 - travel_turns` (modest positive, below good attacks)
  - Sun-safety check required
- [ ] Add `"consolidate"` candidate type
- [ ] Include consolidation candidates in global priority queue
- [ ] Test: planet with 50 ships and production 1 far from enemies generates consolidation candidate
- [ ] Benchmark: expect higher ship utilization in mid/late game

---

## Phase 3: Strategic Awareness

### Task 3.1: Economy Tracking
**Fixes:** Root Cause #7 — no opponent economy tracking
**Files:** `main.py`
**Impact:** +50-100 leaderboard positions

- [ ] Add `_compute_economy(planets, fleets, player)` function returning:
  - `my_production`, `my_ships`, `my_planet_count`
  - `enemy_production`, `enemy_ships`, `enemy_planet_count`
  - `neutral_production`, `neutral_count`
  - `production_advantage` (my - enemy)
  - `ship_advantage` (my - enemy)
- [ ] Call at start of `decide_with_trace()`, store in decision trace
- [ ] Use economy to adjust aggression:
  - `production_advantage > 5`: prefer defense + neutral expansion (play safe)
  - `production_advantage < -3`: prefer attacks on enemy economy (catch up)
  - `neutral_production > my_production`: prioritize neutral capture
- [ ] Implement as score multipliers on attack vs expand candidates:
  - When behind: attack score *= 1.5, expand score *= 0.8
  - When ahead: attack score *= 0.7, expand score *= 1.3, defense candidates get priority
- [ ] Test: when we have 20 production and enemy has 10, attack scores decrease
- [ ] Benchmark vs nearest_sniper

### Task 3.2: 4-Player Target Selection
**Fixes:** Root Cause #11 — no 4-player awareness
**Files:** `main.py`

- [ ] Detect number of active players from observation
- [ ] In 4-player games, compute per-enemy economy stats
- [ ] Target selection logic:
  - If we're leading: avoid attacks, defend + neutrals (don't make enemies)
  - If someone else is leading: focus attacks on leader
  - If we're weakest: turtle and grab neutrals, avoid provoking
- [ ] Add `attack_priority` per enemy player based on their production rank
- [ ] Weight attack candidates by target owner's priority
- [ ] Test: in 4p game, don't attack weakest player when strongest exists

### Task 3.3: Strategic Map Positioning
**Fixes:** Root Cause #12 — no strategic map positioning
**Files:** `main.py`

- [ ] Add `_positional_value(planet, my_planets, enemy_planets)` function
  - Bonus for planets near enemy territory (offensive staging)
  - Bonus for planets that control access to clusters of neutrals
  - Penalty for isolated planets far from any useful target
- [ ] Add positional score component to both expand and attack candidates
- [ ] Weight: `positional_value * 0.2` (modest, doesn't override production value)
- [ ] Test: planet adjacent to 3 enemy planets valued higher than isolated planet with same production

---

## Phase 4: Combat Improvements

### Task 4.1: Coordinated Multi-Source Attacks
**Fixes:** Root Cause #1 — no coordinated attacks
**Files:** `main.py`
**Impact:** +50-100 leaderboard positions

- [ ] After generating individual candidates, identify high-value targets where no single source can afford attack
- [ ] Add `_plan_coordinated_attack(target, my_planets, source_budgets, step)`:
  - Sum available ships from multiple nearby sources
  - If total >= ships_needed, plan multi-source attack
  - Assign ships proportionally based on proximity (closer sources send more)
  - Account for arrival timing — stagger if needed so fleets arrive same turn
- [ ] Create synthetic `"coordinated_attack"` candidates
- [ ] Include in global priority queue with high scores
- [ ] Mark contributing sources' budgets as committed
- [ ] Test: enemy planet with 100 ships captured by 3 sources sending 40 each
- [ ] Benchmark vs nearest_sniper

### Task 4.2: Better Attack Margin with Reinforcement Awareness
**Fixes:** Root Cause #14 — attack margin doesn't account for enemy reinforcements
**Files:** `main.py`

- [ ] Add `_estimate_enemy_reinforcement(target, enemy_planets, my_travel_turns)`:
  - Check if enemy has planets within reinforcement range of target
  - Estimate how many ships enemy can send before our fleet arrives
  - `reinforcement_risk = sum(enemy.ships for nearby enemies if enemy_travel < my_travel)`
- [ ] Scale attack margin by reinforcement risk:
  - Low risk (no nearby enemy planets): `margin = max(2, production // 2 + 1)` (current)
  - Medium risk: `margin = max(5, production + reinforcement_estimate * 0.3)`
  - High risk: skip attack entirely (will fail)
- [ ] Add `reinforcement_risk` to attack candidate score_components
- [ ] Test: attack on enemy planet near 3 other enemy planets gets higher margin or is rejected

### Task 4.3: Improved Defense — Preemptive Reinforcement
**Fixes:** Root Cause #6 — defense is purely reactive
**Files:** `main.py`

- [ ] Add `_compute_threat_level(my_planet, enemy_planets, enemy_fleets)`:
  - Score based on nearby enemy ship concentrations
  - Factor in enemy fleets heading generally toward our territory
  - Consider enemy production near our planet
- [ ] Generate preemptive reinforcement candidates:
  - When a high-production planet has threat_level > threshold and low garrison
  - Send ships from safer planets before enemy actually launches
- [ ] Score: `threat_level * planet.production - ships_needed - travel_cost`
- [ ] Integrate into global candidate queue as `"preemptive_defense"` type
- [ ] Test: planet with production 5 near enemy 100-ship planet generates defense candidate
- [ ] Don't over-defend: cap preemptive reinforcement at 2x expected threat

### Task 4.4: Multi-Fleet Combat Awareness
**Fixes:** Root Cause — no awareness of 3rd-party fleets in combat
**Files:** `main.py`

- [ ] When computing ships_needed for attack, check if other enemy fleets also target same planet
- [ ] In 4-player: if two enemies both send fleets to same planet, largest force fights second largest first (per combat rules)
- [ ] Use this to exploit: if enemy A and B both sending to neutral P, wait and attack the weakened survivor
- [ ] Or: if our fleet and enemy fleet arrive same turn, combat rules apply — compute expected outcome
- [ ] Test: don't attack planet where larger enemy fleet also arriving same turn

---

## Phase 5: Orbit & Comet

### Task 5.1: Fix Orbit Intercept Timing
**Fixes:** Root Cause #13 — orbit prediction uses wrong time reference
**Files:** `prediction.py`, `main.py`

- [ ] Change `sample_orbit_intercept` to accept `current_step` parameter
- [ ] Change loop: `absolute_turn = current_step + future_turn`
- [ ] Pass `predict_orbit_position(initial_target, angular_velocity, absolute_turn)`
- [ ] Compare `timing_error = abs(travel_turns - future_turn)` (future offset, not absolute)
- [ ] Update call site in `main.py` to pass `step`
- [ ] Test: at step 200, orbit prediction gives sensible future positions (not past)
- [ ] Verify sun-safety check uses predicted position

### Task 5.2: Comet Capture
**Fixes:** Root Cause #4 — no comet handling
**Files:** `main.py`

- [ ] Parse `comet_planet_ids` from observation
- [ ] Parse `comets` data (paths, path_index) for lifetime estimation
- [ ] Add `_estimate_comet_lifetime(comet_id, comets_data)`:
  - `remaining_steps = len(path) - path_index`
  - `remaining_turns = remaining_steps` (comet moves 1 path step per turn)
- [ ] Add `_generate_comet_candidates(obs, my_planets, planets, step, player)`:
  - For each unowned comet: compute capture cost, arrival time, remaining life after capture
  - Score: `1 * remaining_life_after_arrival - ships_needed - travel_turns`
  - Reject if arrival >= remaining lifetime
- [ ] Add `"comet"` candidate type, include in global queue
- [ ] Add comet evacuation: if we own a comet about to expire, launch all ships to nearest safe planet
- [ ] Test: comet with 30 turns remaining and 5 garrison generates positive-score capture candidate
- [ ] Test: comet with 3 turns remaining gets rejected

### Task 5.3: Comet Path Prediction for Interception
**Files:** `main.py`, `prediction.py`

- [ ] Use comet `paths` data to predict future comet positions
- [ ] Aim fleet at predicted future comet position (like orbit intercept)
- [ ] Comets move at 4.0 units/turn — fast, so timing is critical
- [ ] If comet is moving toward us, send fleet to intercept point along path
- [ ] If comet is moving away, probably not worth chasing

---

## Phase 6: Endgame & Polish

### Task 6.1: Improved Endgame Scoring
**Files:** `main.py`

- [ ] Start endgame evaluation earlier (turn 400 instead of 470)
- [ ] At turn 400+, compute: "if game ended now, who wins?"
- [ ] If winning: play defensive, don't risk flips
- [ ] If losing: aggressive last-ditch attacks on high-value targets
- [ ] At turn 470+: any ship in transit still counts for final score
  - Launch all excess ships even if target won't be captured
  - Fleet ships count toward final score
- [ ] Preserve garrison on owned planets proportional to nearby threats

### Task 6.2: Fleet Speed Optimization (General)
**Fixes:** Root Cause #8 — small-fleet speed penalty ignored
**Files:** `main.py`, `geometry.py`

- [ ] For ALL phases (not just early), consider fleet speed in scoring
- [ ] Add `speed_efficiency = 1.0 / turns_to_reach(distance, ships_needed)` to score
- [ ] When ships_needed is very low and distance is high, send more ships for speed
- [ ] `effective_ships = max(ships_needed, _min_ships_for_arrival(distance, max_acceptable_turns))`
- [ ] `max_acceptable_turns` scales with game phase: 15 early, 25 mid, 10 late
- [ ] Test: sending 20 ships to target 40 units away preferred over sending 5 ships

### Task 6.3: Reserve Policy Retuning
**Fixes:** Root Cause #10 — reserve policy tuned for random
**Files:** `main.py`

- [ ] Make reserves dynamic based on threat level:
  - Low threat (no nearby enemies): `reserve = max(1, production // 3)`
  - Medium threat: `reserve = max(3, production)`
  - High threat (enemy fleet incoming or nearby): `reserve = max(5, production * 2)`
- [ ] Compute threat level per planet using Task 4.3's `_compute_threat_level()`
- [ ] Test: planet near enemy with 100 ships keeps higher reserve than safe backline planet

---

## Phase 7: Advanced Features

### Task 7.1: Attack Timing — Strike When Enemy Is Weak
**Files:** `main.py`

- [ ] Track enemy planet ship counts over time (requires memory across turns — use planet.ships from obs)
- [ ] Detect when enemy planet just launched ships (garrison dropped significantly)
- [ ] Prioritize attacks on freshly-weakened planets: add `weakness_bonus` to attack score
- [ ] `weakness_bonus = max(0, expected_garrison - actual_garrison) * 3`
- [ ] The "expected" garrison = production * turns_since_game_start (rough estimate)
- [ ] Test: enemy planet that dropped from 80 to 10 ships gets attack priority boost

### Task 7.2: Avoid Launching Into Enemy Fleets
**Files:** `main.py`

- [ ] Before finalizing a move, check if our fleet path will cross any enemy fleet heading toward us
- [ ] If enemy fleet is larger and will arrive at our target first, reconsider
- [ ] If enemy fleet will intercept our fleet path near a planet, our ships might get absorbed into wrong combat
- [ ] Add `fleet_path_risk` check: scan enemy fleets for path intersection with our planned trajectory

### Task 7.3: Production Island Detection
**Files:** `main.py`

- [ ] Identify clusters of nearby planets ("islands")
- [ ] Prioritize completing island ownership (capture all planets in a cluster)
- [ ] A half-captured island means enemy can reinforce from within
- [ ] Score bonus for targets that complete island control

### Task 7.4: Feint/Distraction Detection
**Files:** `main.py`

- [ ] If enemy sends many small fleets at different planets simultaneously, it's a probe/feint
- [ ] Don't over-react: small fleets get absorbed by garrison production
- [ ] Only reinforce against fleets that actually threaten planet survival
- [ ] Threshold: `threat.fleet.ships > target.ships + target.production * threat.arrival_turns`

---

## Phase 8: Validation & Submission Loop

### Task 8.1: Comprehensive Benchmark Suite
**Files:** `evaluate.py`

- [ ] Create benchmark script that runs all test scenarios:
  ```bash
  # Full benchmark (run before every submission)
  python evaluate.py --start-seed 1 --games 100 --opponents random --summary results/vs_random.json
  python evaluate.py --start-seed 1 --games 100 --opponents opponents/nearest_sniper.py --summary results/vs_sniper.json
  python evaluate.py --start-seed 1 --games 50 --opponents opponents/v1_baseline.py --summary results/vs_v1.json
  python evaluate.py --start-seed 1 --games 20 --players 4 --summary results/4player.json
  ```
- [ ] Promotion criteria: new version must beat v1_baseline on all benchmarks

### Task 8.2: Kaggle Replay Feedback Loop
**Files:** `analyze_replays.py`

- [ ] After each submission, download 5 loss replays
- [ ] Analyze common failure patterns
- [ ] Add specific counter-strategies for observed opponent behaviors
- [ ] Track: "what beat us?" and address each pattern

### Task 8.3: Submission Packaging Verification
**Files:** submission pipeline

- [ ] Verify `submission/` directory matches root source files
- [ ] Run smoke test with submission package (not root files)
- [ ] Check no imports fail, no file-not-found errors
- [ ] Verify `agent(obs)` returns valid moves for edge-case observations:
  - Step 0 (game start)
  - Step 499 (last turn)
  - All planets owned by us (no targets)
  - All planets owned by enemy (no sources)
  - Large fleet incoming (threat detection)

---

## Task Dependency Graph

```
Phase 0 (Testing Infrastructure)
  └── 0.1 Starter Agent Benchmark ──┐
  └── 0.2 Self-Play Evaluation ─────┤
  └── 0.3 4-Player Evaluation ──────┤
  └── 0.4 Replay Analysis ──────────┤
                                     │
Phase 1 (Early Game) ←───────────────┘
  └── 1.1 Early Rush Scoring
  └── 1.2 Fleet Speed in Early Game
  └── 1.3 Lower Early Reserves
         │
Phase 2 (Resource Efficiency)
  └── 2.1 Fleet-In-Flight Tracking
  └── 2.2 Global Priority Queue
  └── 2.3 Consolidation
         │
Phase 3 (Strategic Awareness)
  └── 3.1 Economy Tracking
  └── 3.2 4-Player Target Selection (needs 0.3)
  └── 3.3 Map Positioning
         │
Phase 4 (Combat)
  └── 4.1 Coordinated Attacks (needs 2.2)
  └── 4.2 Better Attack Margin
  └── 4.3 Preemptive Defense
  └── 4.4 Multi-Fleet Combat
         │
Phase 5 (Orbit & Comet)
  └── 5.1 Fix Orbit Timing
  └── 5.2 Comet Capture
  └── 5.3 Comet Interception (needs 5.2)
         │
Phase 6 (Endgame & Polish)
  └── 6.1 Endgame Scoring
  └── 6.2 Fleet Speed General
  └── 6.3 Reserve Retuning (needs 4.3)
         │
Phase 7 (Advanced)
  └── 7.1 Strike When Weak
  └── 7.2 Avoid Enemy Fleets
  └── 7.3 Island Detection
  └── 7.4 Feint Detection
         │
Phase 8 (Validation)
  └── 8.1 Benchmark Suite
  └── 8.2 Replay Feedback
  └── 8.3 Submission Verification
```

## Root Cause → Task Mapping

| # | Root Cause | Primary Task | Supporting Tasks |
|---|-----------|-------------|-----------------|
| 1 | No coordinated attacks | 4.1 | 2.2 |
| 2 | No fleet-in-flight tracking | 2.1 | — |
| 3 | No consolidation | 2.3 | 3.3 |
| 4 | No comet handling | 5.2 | 5.3 |
| 5 | Greedy per-source allocation | 2.2 | — |
| 6 | Purely reactive defense | 4.3 | 7.4, 6.3 |
| 7 | No economy tracking | 3.1 | 3.2 |
| 8 | Small-fleet speed penalty | 1.2 | 6.2 |
| 9 | No early-game rush | 1.1 | 1.2, 1.3 |
| 10 | Reserves tuned for random | 1.3 | 6.3 |
| 11 | No 4-player awareness | 3.2 | 0.3 |
| 12 | No map positioning | 3.3 | 7.3 |
| 13 | Orbit timing bug | 5.1 | — |
| 14 | Attack margin too simple | 4.2 | 4.4 |
| — | No opponent benchmarks | 0.1, 0.2 | 8.1, 8.2 |
| — | No replay analysis | 0.4 | 8.2 |
| — | No strike-when-weak | 7.1 | — |
| — | Fleet path risk | 7.2 | — |
| — | No feint detection | 7.4 | — |

## Estimated Total Effort

| Phase | Tasks | Estimated Days |
|-------|-------|---------------|
| 0 | 4 | 1-2 |
| 1 | 3 | 1-2 |
| 2 | 3 | 2-3 |
| 3 | 3 | 2-3 |
| 4 | 4 | 3-4 |
| 5 | 3 | 2-3 |
| 6 | 3 | 1-2 |
| 7 | 4 | 2-3 |
| 8 | 3 | 1-2 |
| **Total** | **30** | **~15-24 days** |

**Submit after each phase.** Don't wait until everything is done. Kaggle leaderboard feedback is the most valuable signal.
