# Orbit Wars: Why We Score 521 and How to Fix It

## Diagnosis: Why 521?

The agent wins 99% against `random` but scores 521 on Kaggle. This is not a bug — it's a **strategy gap**. The `random` opponent makes uniformly terrible moves. Beating it proves only that the code runs and doesn't crash. Every competent Kaggle submission also beats random. The leaderboard ranks agents against *each other*, and 521 means we lose to most of them.

### Root Causes (Ordered by Impact)

#### 1. No Coordinated Attacks
Each source planet independently picks targets via `_select_budgeted_candidates()`. There is no way to converge fleets from 3 planets onto one strong enemy planet. Against good opponents, single-source attacks get outproduced by enemy garrisons + reinforcements. Coordinated attacks are the single biggest capability gap.

#### 2. No Fleet-In-Flight Tracking
The agent doesn't know what it already sent. If planet A launches 30 ships at target T on turn 50, planet B might also launch 30 ships at T on turn 51. Result: 60 ships arrive when 31 were needed — 29 wasted. Against random this doesn't matter. Against real opponents, every wasted ship is a lost battle elsewhere.

#### 3. No Consolidation
Ships stranded on captured low-production backline planets (production 1-2) never move. They sit idle for hundreds of turns. The plan.md mentions `consolidate` as a candidate type but it was never implemented. A production-1 planet with 50 ships deep in friendly territory is 50 ships doing nothing.

#### 4. No Comet Handling
Comets spawn every 100 turns (at steps 50, 150, 250, 350, 450). They're free production-1 planets with low garrisons. The `comet_planet_ids` observation field is never read. The `comets` paths data is never used. Free economy left on the table every game.

#### 5. Greedy Per-Source, Not Global Optimization
Budget selection happens per-source (`_select_budgeted_candidates` called per `mine in my_planets`). Source A might grab a marginal target (score 50) while source B needed those ships for a critical attack (score 500). A global priority queue across all sources would fix this.

#### 6. Defense Is Purely Reactive
`_detect_incoming_threats()` only sees enemy fleets already launched. It can't anticipate that the enemy will launch from their 200-ship planet next turn. No preemptive reinforcement, no garrison buildup on frontline planets. Against smart opponents who probe before attacking, the agent is always one step behind.

#### 7. No Opponent Economy Tracking
The agent doesn't compute total enemy production, total enemy ships, or production advantage. It can't decide "I'm ahead economically, play safe" vs "I'm behind, need to attack NOW." Every decision is made locally without global strategic awareness.

#### 8. Small-Fleet Speed Penalty Ignored
Fleet speed formula: `1.0 + 5.0 * (log(ships)/log(1000))^1.5`. A 1-ship fleet moves 1.0 units/turn. A 100-ship fleet moves ~3.3 units/turn. Sending tiny fleets to distant targets means they arrive 3x slower. The agent sends `ships_needed` which for cheap neutrals can be very small (e.g., 6 ships to capture a 5-garrison planet), resulting in a fleet that crawls across the map.

#### 9. No Early-Game Rush Optimization
The critical first 50 turns determine who gets the best neutrals. The agent treats all phases the same — score by `production * remaining_turns - ship_cost - travel_cost`. It doesn't understand that turn 1 is a *race* to grab high-production neutrals before the opponent. The first player to reach production 20+ snowballs.

#### 10. Reserve Policy Tuned for Random
Phase thresholds (EARLY_GAME_END=150, LATE_GAME_START=400) and reserves (max(3, production) early, max(5, production) mid) were designed against random. Against aggressive opponents, keeping 5 ships in reserve on a production-3 planet when you could be capturing a production-5 neutral is too conservative. Against defensive opponents, the reserves might be too low.

#### 11. No 4-Player Awareness
Kaggle games can be 2-player or 4-player. In 4-player games, attacking the strongest player while the other two grow is suicide. The agent has zero logic for "who is winning" or "who should I attack." It attacks any non-owned planet, which in a 4p game means potentially attacking the weakest player while the strongest grows unchecked.

#### 12. No Strategic Map Positioning
A production-3 planet adjacent to two enemy planets is far more valuable to hold than a production-5 planet surrounded by friendlies. The agent scores targets purely by `production * remaining_turns` with no positional awareness. Top agents consider chokepoints, territory boundaries, and proximity to enemy economy.

#### 13. Orbit Prediction Uses Wrong Time Reference
`sample_orbit_intercept` iterates `intercept_turn` from 1 to 80, but these are turns from game start (`initial_planet` position), not turns from *now*. The prediction uses `predict_orbit_position(initial_target, angular_velocity, intercept_turn)` which gives absolute position at game turn `intercept_turn`. At step 200, sampling turn 1-80 gives positions from the past. This needs to be `step + future_turn`.

#### 14. Attack Margin Doesn't Account for Enemy Reinforcements
`_attack_margin(target) = max(2, target.production // 2 + 1)` is a tiny buffer. Against a smart opponent, if you're sending ships to their planet, they'll see your fleet and reinforce with 100+ ships. The margin should scale with enemy economy and proximity of enemy reinforcement sources.

---

## Solution A: Improve Existing Architecture

Keep the rule-based candidate-scoring approach but fix the critical gaps. This is lower-risk and can be done incrementally.

### A1. Global Priority Queue (Impact: Critical)

**Current:** Per-source greedy selection.
**Fix:** Score ALL candidates from ALL sources globally, then allocate from the top down.

```python
def _select_global_candidates(all_candidates, source_budgets):
    selected = []
    for candidate in sorted(all_candidates, key=lambda c: c["score"], reverse=True):
        src = candidate["source_planet_id"]
        budget = source_budgets.get(src, 0)
        reserve = candidate["desired_reserve"]
        if candidate["ships"] > budget - reserve:
            candidate["legal"] = False
            candidate["rejection_reason"] = "global_budget_exhausted"
            continue
        if not candidate["legal"]:
            continue
        selected.append(candidate)
        source_budgets[src] -= candidate["ships"]
    return selected
```

### A2. Fleet-In-Flight Tracking (Impact: Critical)

**Problem:** Double-sending ships to same target.
**Fix:** Track pending attacks per target. Reduce `ships_needed` by ships already in flight.

```python
def _pending_attacks(my_fleets, targets, planets):
    """Sum my fleet ships heading toward each target planet."""
    pending = {}  # target_id -> total_ships_incoming
    for fleet in my_fleets:
        for target in targets:
            dist = _first_blocking_distance(fleet, target, planets)
            if dist is not None:
                pending[target.id] = pending.get(target.id, 0) + fleet.ships
    return pending

# In candidate generation:
already_sent = pending.get(target.id, 0)
ships_needed = max(1, base_ships_needed - already_sent)
```

### A3. Coordinated Multi-Source Attacks (Impact: High)

**Problem:** Single source can't afford to take strong enemy planets.
**Fix:** After global scoring, identify high-value targets that no single source can afford alone. Pool ships from multiple sources.

```python
def _plan_coordinated_attack(target, sources, source_budgets):
    """Plan a multi-source attack on a single target."""
    total_available = sum(
        max(0, source_budgets[s.id] - _desired_reserve(s, step, 0))
        for s in sources
    )
    if total_available < ships_needed:
        return None  # Can't afford even with coordination

    moves = []
    remaining_need = ships_needed
    # Sort sources by travel time (closest first for timing)
    for source in sorted(sources, key=lambda s: distance_to_target(s, target)):
        available = source_budgets[source.id] - _desired_reserve(source, step, 0)
        send = min(available, remaining_need)
        if send > 0:
            moves.append([source.id, angle_to(source, target), send])
            remaining_need -= send
        if remaining_need <= 0:
            break
    return moves
```

### A4. Consolidation Moves (Impact: High)

**Problem:** Ships idle on backline planets.
**Fix:** Add `consolidate` candidate type. Move ships from low-value planets toward frontline high-production planets or staging areas.

```python
def _generate_consolidation_candidates(my_planets, enemy_planets, step):
    candidates = []
    # Find frontline planets (closest to enemies)
    frontline = _identify_frontline(my_planets, enemy_planets)
    backline = [p for p in my_planets if p not in frontline and p.ships > 10]

    for source in backline:
        for target in frontline:
            if source.id == target.id:
                continue
            # Move excess ships (keep small reserve)
            ships_to_send = source.ships - max(2, source.production)
            if ships_to_send <= 0:
                continue
            distance = geometry.distance_xy(source.x, source.y, target.x, target.y)
            if geometry.shot_hits_sun((source.x, source.y), (target.x, target.y)):
                continue
            travel = geometry.turns_to_reach(distance, ships_to_send)
            score = ships_to_send * 0.5 - travel  # Value: getting idle ships active
            candidates.append(make_candidate(
                "consolidate", source, target, ships_to_send, score
            ))
    return candidates
```

### A5. Comet Capture (Impact: Medium)

**Problem:** Free production ignored.
**Fix:** Parse `comet_planet_ids`, estimate comet lifetime from path data, capture if profitable.

```python
def _generate_comet_candidates(obs, my_planets, step):
    comet_ids = set(_obs_get(obs, "comet_planet_ids", []))
    comets_data = _obs_get(obs, "comets", [])
    candidates = []

    comet_planets = [p for p in planets if p.id in comet_ids and p.owner != player]

    for comet in comet_planets:
        # Estimate remaining lifetime from path data
        remaining_life = _estimate_comet_lifetime(comet, comets_data)
        if remaining_life < 10:
            continue  # Not worth chasing

        for source in my_planets:
            ships_needed = comet.ships + 1
            distance = geometry.distance_xy(source.x, source.y, comet.x, comet.y)
            travel = geometry.turns_to_reach(distance, ships_needed)

            if travel >= remaining_life:
                continue  # Won't arrive before comet leaves

            production_value = 1 * (remaining_life - travel)  # comet production = 1
            score = production_value - ships_needed - travel
            if score > 0:
                candidates.append(make_candidate(
                    "comet", source, comet, ships_needed, score
                ))
    return candidates
```

### A6. Economy-Aware Strategy (Impact: High)

**Problem:** No global strategic awareness.
**Fix:** Compute production totals and adjust aggression.

```python
def _compute_economy(planets, player):
    my_production = sum(p.production for p in planets if p.owner == player)
    my_ships = sum(p.ships for p in planets if p.owner == player)
    enemy_production = sum(p.production for p in planets if p.owner >= 0 and p.owner != player)
    enemy_ships = sum(p.ships for p in planets if p.owner >= 0 and p.owner != player)
    neutral_production = sum(p.production for p in planets if p.owner == -1)
    return {
        "my_production": my_production,
        "my_ships": my_ships,
        "enemy_production": enemy_production,
        "enemy_ships": enemy_ships,
        "neutral_production": neutral_production,
        "production_advantage": my_production - enemy_production,
        "ship_advantage": my_ships - enemy_ships,
    }

# Adjust strategy:
# - production_advantage > 5: play safe, expand neutrals, defend
# - production_advantage < -3: aggressive attacks on enemy production
# - neutral_production > 10: prioritize neutral capture over attacks
```

### A7. Minimum Fleet Size for Speed (Impact: Medium)

**Problem:** Tiny fleets crawl.
**Fix:** Enforce minimum fleet size for distant targets so fleets arrive in reasonable time.

```python
def _min_fleet_for_distance(distance, max_arrival_turns=15):
    """Compute minimum ships needed to arrive within max_arrival_turns."""
    # Binary search for minimum ships where turns_to_reach <= max_arrival_turns
    lo, hi = 1, 1000
    while lo < hi:
        mid = (lo + hi) // 2
        if geometry.turns_to_reach(distance, mid) <= max_arrival_turns:
            hi = mid
        else:
            lo = mid + 1
    return lo

# When computing ships_needed:
speed_minimum = _min_fleet_for_distance(distance, max_arrival_turns=20)
ships_needed = max(base_ships_needed, speed_minimum)
```

### A8. Fix Orbit Intercept Timing (Impact: Medium)

**Problem:** `sample_orbit_intercept` uses absolute turns, not relative to current step.
**Fix:** Pass current step and compute future positions relative to now.

```python
def sample_orbit_intercept(source, target, initial_target, angular_velocity,
                           ships, current_step, max_future_turns=80,
                           timing_tolerance=2.0):
    best_sample = None
    best_error = float("inf")

    for future_turn in range(1, max_future_turns + 1):
        absolute_turn = current_step + future_turn  # <-- FIX: relative to now
        predicted_x, predicted_y = predict_orbit_position(
            initial_target, angular_velocity, absolute_turn
        )
        distance = geometry.distance_xy(source.x, source.y, predicted_x, predicted_y)
        travel_turns = geometry.turns_to_reach(distance, ships)
        timing_error = abs(travel_turns - future_turn)  # <-- compare with future offset

        if timing_error < best_error:
            best_error = timing_error
            best_sample = { ... }

    if best_sample is None or best_sample["timing_error"] > timing_tolerance:
        return None
    return best_sample
```

### A9. Early-Game Rush Priority (Impact: High)

**Problem:** No urgency in capturing high-production neutrals early.
**Fix:** In the first 30 turns, weight neutral capture score much higher. First player to 20+ production wins the snowball.

```python
def _early_game_bonus(step, target, travel_turns):
    if step > 50 or target.owner != -1:
        return 0
    # Massive bonus for grabbing high-production neutrals early
    # Production-5 planet captured turn 5 = 5 * 495 = 2475 lifetime value
    urgency = max(0, 30 - step - travel_turns) * target.production * 5
    return urgency
```

### A10. Smarter Defense: Anticipate Threats (Impact: Medium-High)

**Problem:** Only defends against visible fleets.
**Fix:** Also preemptively reinforce planets that are close to strong enemy planets, even without visible incoming fleets.

```python
def _preemptive_defense_score(my_planet, enemy_planets):
    """Score how threatened a planet is based on nearby enemy economy."""
    threat_score = 0
    for enemy in enemy_planets:
        dist = geometry.distance_xy(my_planet.x, my_planet.y, enemy.x, enemy.y)
        if dist < 30:  # Within striking range
            threat_score += enemy.ships / max(1, dist)
    return threat_score

# High threat_score planets should maintain larger garrisons
# and be prioritized for consolidation reinforcements
```

### A11. 4-Player Target Selection (Impact: Medium)

**Problem:** Attacks any non-owned planet indiscriminately.
**Fix:** In 4-player games, identify the leader and avoid attacking weak players. Focus on the strongest threat or expand neutrals.

```python
def _choose_attack_targets(planets, player, step):
    players = {}
    for p in planets:
        if p.owner >= 0:
            players.setdefault(p.owner, {"production": 0, "ships": 0})
            players[p.owner]["production"] += p.production
            players[p.owner]["ships"] += p.ships

    my_stats = players.get(player, {"production": 0, "ships": 0})
    enemies = {k: v for k, v in players.items() if k != player}

    if len(enemies) > 1:
        # 4-player: attack leader or grab neutrals, don't bully weakest
        leader = max(enemies, key=lambda k: enemies[k]["production"])
        return leader  # Prefer attacking the leader
    return None  # 2-player: attack the only enemy
```

### A12. Overcommit Prevention for Attacks (Impact: Medium)

**Current:** `_attack_overextends_source` only checks if ships > 75% of available after reserve, and only for production >= 5.
**Fix:** Account for enemy reinforcement possibility. If target is close to enemy planets with high ship counts, increase the margin or reject the attack.

```python
def _can_enemy_reinforce(target, enemy_planets, my_travel_turns):
    """Check if enemy can reinforce target before our fleet arrives."""
    for enemy_src in enemy_planets:
        if enemy_src.id == target.id:
            continue
        dist = geometry.distance_xy(enemy_src.x, enemy_src.y, target.x, target.y)
        enemy_travel = geometry.turns_to_reach(dist, enemy_src.ships)
        if enemy_travel <= my_travel_turns and enemy_src.ships > 10:
            return True, enemy_src.ships
    return False, 0
```

### Implementation Priority Order

| Priority | Task | Expected LB Impact | Effort |
|----------|------|---------------------|--------|
| 1 | A9: Early-game rush | +100-200 | Low |
| 2 | A1: Global priority queue | +50-100 | Medium |
| 3 | A2: Fleet-in-flight tracking | +50-100 | Medium |
| 4 | A6: Economy-aware strategy | +50-100 | Medium |
| 5 | A3: Coordinated attacks | +50-100 | High |
| 6 | A4: Consolidation | +30-50 | Medium |
| 7 | A8: Fix orbit intercept | +20-40 | Low |
| 8 | A7: Min fleet size for speed | +20-30 | Low |
| 9 | A5: Comet capture | +10-30 | Medium |
| 10 | A10: Preemptive defense | +20-40 | Medium |
| 11 | A11: 4-player awareness | +20-40 | Medium |
| 12 | A12: Better overcommit | +10-20 | Low |

### Testing Strategy for Solution A

**Stop testing against only `random`.** The agent already beats random 99%. Every future benchmark must include:

1. **Self-play**: current version vs previous version on fixed seeds
2. **Multiple opponents**: test against the starter agent (nearest_sniper) at minimum
3. **4-player games**: test with 4 copies of the agent or mixed opponents
4. **Kaggle replay analysis**: download replays from Kaggle losses, identify specific failure patterns

```bash
# Self-play: new vs old
python evaluate.py --start-seed 1 --games 100 --opponents submission/main.py \
  --summary results/self_play_v2_vs_v1.json

# 4-player game
python -c "
from kaggle_environments import make
env = make('orbit_wars', configuration={'episodeSteps': 500})
env.run(['main.py', 'main.py', 'main.py', 'main.py'])
print([(i, s.reward) for i, s in enumerate(env.steps[-1])])
"
```

---

## Solution B: Start From Scratch with a Competitive Architecture

The current architecture has fundamental design limitations. A ground-up rewrite with a proper game-tree / simulation-based approach would be more competitive.

### B1. Architecture Overview

```
obs -> GameState -> Simulator -> MCTS/Minimax -> ActionSelector -> moves
                        |
                    Evaluator (heuristic board value)
```

Instead of candidate scoring, simulate future game states and choose the action sequence that leads to the best board position. This is how top agents in similar Kaggle competitions (Halite, Lux AI) work.

### B2. GameState Object

A proper game state that can be copied, mutated, and evaluated.

```python
class GameState:
    def __init__(self, obs):
        self.step = obs["step"]
        self.player = obs["player"]
        self.planets = [Planet(*p) for p in obs["planets"]]
        self.fleets = [Fleet(*f) for f in obs["fleets"]]
        self.angular_velocity = obs.get("angular_velocity", 0)
        self.comet_ids = set(obs.get("comet_planet_ids", []))

    def copy(self):
        """Deep copy for simulation."""
        ...

    def apply_actions(self, player_actions):
        """Apply actions and advance one tick."""
        # 1. Fleet launch
        # 2. Production
        # 3. Fleet movement
        # 4. Planet rotation
        # 5. Combat resolution
        ...

    def get_legal_actions(self, player):
        """Generate all meaningful action combinations."""
        ...

    def evaluate(self, player):
        """Heuristic board evaluation."""
        ...

    @property
    def my_production(self):
        return sum(p.production for p in self.planets if p.owner == self.player)

    @property
    def is_terminal(self):
        return self.step >= 500 or len(set(p.owner for p in self.planets if p.owner >= 0)) <= 1
```

### B3. Fast Forward Simulator

A lightweight re-implementation of the game physics for internal simulation. The Kaggle environment is too slow for Monte Carlo sampling.

```python
class FastSimulator:
    """Lightweight game physics for lookahead."""

    def step(self, state, actions_by_player):
        """Advance state by one turn. Mutates state in-place."""
        self._launch_fleets(state, actions_by_player)
        self._produce_ships(state)
        self._move_fleets(state)
        self._rotate_planets(state)
        self._resolve_combat(state)
        state.step += 1

    def simulate_n_turns(self, state, my_actions, opponent_model, n_turns):
        """Simulate n turns with given actions and opponent model."""
        state = state.copy()
        for turn in range(n_turns):
            if turn == 0:
                actions = {state.player: my_actions}
            else:
                actions = {state.player: self._greedy_actions(state, state.player)}
            # Predict opponent actions
            for opp in self._get_opponents(state):
                actions[opp] = opponent_model.predict(state, opp)
            self.step(state, actions)
        return state

    def _move_fleets(self, state):
        """Move fleets, check sun/planet collisions."""
        surviving = []
        for fleet in state.fleets:
            speed = fleet_speed(fleet.ships)
            new_x = fleet.x + speed * math.cos(fleet.angle)
            new_y = fleet.y + speed * math.sin(fleet.angle)

            # Check sun collision
            if segment_intersects_circle(fleet.x, fleet.y, new_x, new_y, 50, 50, 10):
                continue  # Destroyed

            # Check out of bounds
            if new_x < 0 or new_x > 100 or new_y < 0 or new_y > 100:
                continue  # Removed

            # Check planet collisions
            hit_planet = None
            for planet in state.planets:
                if segment_intersects_circle(fleet.x, fleet.y, new_x, new_y,
                                           planet.x, planet.y, planet.radius):
                    hit_planet = planet
                    break

            if hit_planet:
                self._queue_combat(fleet, hit_planet)
            else:
                fleet.x, fleet.y = new_x, new_y
                surviving.append(fleet)
        state.fleets = surviving

    def _resolve_combat(self, state):
        """Resolve all queued combats per game rules."""
        for planet, arrivals in self.combat_queue.items():
            # Group by owner, largest vs second largest
            by_owner = {}
            for fleet in arrivals:
                by_owner[fleet.owner] = by_owner.get(fleet.owner, 0) + fleet.ships

            if not by_owner:
                continue

            sorted_forces = sorted(by_owner.items(), key=lambda x: x[1], reverse=True)
            winner_owner, winner_ships = sorted_forces[0]
            second_ships = sorted_forces[1][1] if len(sorted_forces) > 1 else 0
            surviving = winner_ships - second_ships

            if surviving <= 0:
                continue  # Tie, all destroyed

            if winner_owner == planet.owner:
                planet.ships += surviving
            else:
                if surviving > planet.ships:
                    planet.owner = winner_owner
                    planet.ships = surviving - planet.ships
                else:
                    planet.ships -= surviving
```

### B4. Action Generation: Smart Candidate Pruning

Instead of scoring every source-target pair, generate a small set of *interesting* action combinations.

```python
class ActionGenerator:
    def generate(self, state, player):
        """Generate 20-50 meaningful action sets to evaluate."""
        actions = []

        # 1. Expansion actions (grab best neutral per source)
        actions.extend(self._expansion_actions(state, player))

        # 2. Attack actions (coordinated attacks on weak enemy planets)
        actions.extend(self._attack_actions(state, player))

        # 3. Defense actions (reinforce threatened planets)
        actions.extend(self._defense_actions(state, player))

        # 4. Consolidation (move backline ships forward)
        actions.extend(self._consolidation_actions(state, player))

        # 5. Do nothing (sometimes the best move)
        actions.append([])

        # 6. Combined actions (expand + defend simultaneously)
        actions.extend(self._combined_actions(state, player))

        return actions
```

### B5. Board Evaluation Heuristic

The quality of the evaluation function determines everything. This is where domain knowledge pays off.

```python
class BoardEvaluator:
    def evaluate(self, state, player):
        """Score a board position for player. Higher = better."""
        score = 0

        # 1. Production advantage (most important)
        my_prod = sum(p.production for p in state.planets if p.owner == player)
        enemy_prod = sum(p.production for p in state.planets
                        if p.owner >= 0 and p.owner != player)
        score += (my_prod - enemy_prod) * 100

        # 2. Ship count
        my_ships = (sum(p.ships for p in state.planets if p.owner == player) +
                    sum(f.ships for f in state.fleets if f.owner == player))
        enemy_ships = (sum(p.ships for p in state.planets
                         if p.owner >= 0 and p.owner != player) +
                      sum(f.ships for f in state.fleets
                         if f.owner >= 0 and f.owner != player))
        score += (my_ships - enemy_ships) * 1

        # 3. Planet count
        my_planets = sum(1 for p in state.planets if p.owner == player)
        enemy_planets = sum(1 for p in state.planets
                          if p.owner >= 0 and p.owner != player)
        score += (my_planets - enemy_planets) * 20

        # 4. Territorial control (distance from center of mass)
        score += self._territory_score(state, player)

        # 5. Defensive stability (vulnerable planets)
        score -= self._vulnerability_penalty(state, player)

        # 6. Fleet positioning (ships in transit toward good targets)
        score += self._fleet_value(state, player)

        # 7. Future production (remaining turns * production difference)
        remaining = max(0, 500 - state.step)
        score += (my_prod - enemy_prod) * remaining * 0.5

        return score

    def _vulnerability_penalty(self, state, player):
        """Penalize exposed planets near enemy forces."""
        penalty = 0
        my_planets = [p for p in state.planets if p.owner == player]
        for planet in my_planets:
            for enemy_fleet in state.fleets:
                if enemy_fleet.owner == player:
                    continue
                dist = distance_xy(planet.x, planet.y,
                                  enemy_fleet.x, enemy_fleet.y)
                if dist < 20 and enemy_fleet.ships > planet.ships:
                    penalty += (enemy_fleet.ships - planet.ships) * planet.production
        return penalty
```

### B6. Lookahead Search

With a fast simulator and good evaluation, use shallow lookahead to pick actions.

```python
class LookaheadAgent:
    def __init__(self):
        self.simulator = FastSimulator()
        self.evaluator = BoardEvaluator()
        self.action_gen = ActionGenerator()

    def decide(self, obs):
        state = GameState(obs)
        candidates = self.action_gen.generate(state, state.player)

        best_score = float("-inf")
        best_actions = []

        for action_set in candidates:
            # Simulate 5-10 turns ahead
            future = self.simulator.simulate_n_turns(
                state, action_set,
                opponent_model=GreedyOpponentModel(),
                n_turns=8
            )
            score = self.evaluator.evaluate(future, state.player)

            if score > best_score:
                best_score = score
                best_actions = action_set

        return best_actions
```

### B7. Opponent Modeling

Predict what the opponent will do for more accurate simulation.

```python
class GreedyOpponentModel:
    """Assume opponent plays greedily — captures nearest affordable target."""

    def predict(self, state, opponent_id):
        actions = []
        opp_planets = [p for p in state.planets if p.owner == opponent_id]
        targets = [p for p in state.planets if p.owner != opponent_id]

        for source in opp_planets:
            best_target = min(
                targets,
                key=lambda t: distance_xy(source.x, source.y, t.x, t.y),
                default=None
            )
            if best_target and source.ships > best_target.ships + 1:
                angle = angle_to_xy(source.x, source.y, best_target.x, best_target.y)
                actions.append([source.id, angle, best_target.ships + 1])

        return actions

class MirrorOpponentModel:
    """Assume opponent mirrors our strategy (conservative estimate)."""

    def predict(self, state, opponent_id):
        # Use same action generator but for opponent
        return self.action_gen.generate(state, opponent_id)[0]
```

### B8. Time Management

Kaggle gives 1 second per turn + overage time. Use iterative deepening.

```python
class TimeManagedAgent:
    def decide(self, obs):
        start = time.perf_counter()
        remaining = obs.get("remainingOverageTime", 5.0)
        budget = min(0.8, remaining * 0.1)  # Use 10% of remaining overage

        state = GameState(obs)
        candidates = self.action_gen.generate(state, state.player)

        best_actions = []
        best_score = float("-inf")

        # Iterative deepening: try more candidates until time runs out
        for i, action_set in enumerate(candidates):
            if time.perf_counter() - start > budget:
                break

            future = self.simulator.simulate_n_turns(state, action_set,
                                                      n_turns=5)
            score = self.evaluator.evaluate(future, state.player)

            if score > best_score:
                best_score = score
                best_actions = action_set

        return best_actions
```

### B9. Phase-Specific Strategies

```python
class PhaseStrategy:
    def get_strategy(self, state):
        if state.step < 30:
            return EarlyRushStrategy()
        elif state.step < 150:
            return ExpansionStrategy()
        elif state.step < 350:
            return MidgameStrategy()
        elif state.step < 470:
            return LategameStrategy()
        else:
            return EndgameStrategy()

class EarlyRushStrategy:
    """Turn 0-30: Race to capture high-production neutrals."""

    def generate_actions(self, state, player):
        # Sort all neutrals by production / (ships + travel_time)
        # Greedily assign closest sources to best neutrals
        # Send maximum ships for speed (larger fleet = faster arrival)
        neutrals = sorted(
            [p for p in state.planets if p.owner == -1],
            key=lambda p: p.production / max(1, p.ships),
            reverse=True
        )
        assignments = self._hungarian_assign(state, player, neutrals)
        return assignments

class MidgameStrategy:
    """Turn 150-350: Economy management + targeted attacks."""

    def generate_actions(self, state, player):
        economy = compute_economy(state, player)
        if economy["production_advantage"] > 3:
            # We're ahead: defend, expand remaining neutrals, slow attack
            return self._defensive_expand(state, player)
        elif economy["production_advantage"] < -3:
            # We're behind: aggressive attacks on enemy economy
            return self._aggressive_attack(state, player)
        else:
            # Even: balanced approach
            return self._balanced(state, player)
```

### B10. File Structure for Scratch Rewrite

```
main.py              # Kaggle entrypoint, 50 lines max
game_state.py        # GameState class, parsing, copying
simulator.py         # Fast forward simulation
evaluator.py         # Board evaluation heuristic
action_gen.py        # Smart action candidate generation
search.py            # Lookahead / MCTS
opponent_model.py    # Opponent prediction
geometry.py          # Math utilities (keep existing)
strategy.py          # Phase-specific strategy selection
```

Submit as `tar.gz` with all files.

### Implementation Priority for Solution B

| Phase | Task | Time Estimate |
|-------|------|---------------|
| 1 | GameState + FastSimulator (basic physics) | 2-3 days |
| 2 | BoardEvaluator (heuristic scoring) | 1-2 days |
| 3 | ActionGenerator (expansion + attack) | 1-2 days |
| 4 | Greedy lookahead (simulate top 20 candidates, depth 5) | 1 day |
| 5 | Benchmark vs current agent + random | 0.5 days |
| 6 | Iterate evaluator weights based on Kaggle results | Ongoing |
| 7 | Add coordination, consolidation, comets | 2-3 days |
| 8 | Opponent modeling | 1-2 days |
| 9 | Time management + iterative deepening | 1 day |
| 10 | 4-player adaptations | 1 day |

**Total: ~2-3 weeks for a competitive agent.**

---

## Recommendation

**Start with Solution A, items A9 + A1 + A2 + A6.** These four changes alone should push from 521 to ~300-400 range:
- A9 (early rush) fixes the most common loss pattern: losing the neutral race
- A1 (global queue) fixes wasted ships on marginal targets
- A2 (fleet tracking) fixes double-sending
- A6 (economy tracking) fixes blind aggression when ahead / passive when behind

Then evaluate whether to continue with Solution A or pivot to Solution B based on where the score lands.

**Key insight:** The biggest problem isn't the architecture — it's that the agent was only ever tested against random. Any fix must come with a proper opponent benchmark. Test against the starter agent, against self-play, and analyze Kaggle replays from actual losses.

### Immediate Next Steps

1. Download and analyze replays from Kaggle losses: `kaggle competitions episodes <SUBMISSION_ID>`
2. Implement A9 (early rush) — this is the single highest-impact change
3. Test against starter agent (nearest_sniper from competition download), not just random
4. Implement A1 (global priority queue)
5. Submit and compare leaderboard position
6. Decide A vs B based on results

### What NOT to Spend Time On

- DPO/ML training (premature — the rule-based agent isn't good enough yet to generate useful training data)
- More benchmarks against random (already solved, provides no signal)
- Polishing trace/logging infrastructure (the decision recording is already thorough)
- Orbit prediction refinements (minor impact vs the strategic gaps above)
