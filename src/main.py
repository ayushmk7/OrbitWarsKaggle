import math
import time
from collections import namedtuple
import geometry
import prediction

try:
    from kaggle_environments.envs.orbit_wars.orbit_wars import Planet
except ModuleNotFoundError:
    Planet = namedtuple("Planet", "id owner x y radius ships production")

Fleet = namedtuple("Fleet", "id owner x y angle from_planet_id ships")


AGENT_VERSION = "solution_a_v4_orbit_intercept_fix"
MAX_TURNS = 500
EARLY_GAME_END = 150
LATE_GAME_START = 400
MIN_PROFITABLE_SCORE = 0
MAX_MOVES_PER_SOURCE = 2
ENDGAME_START = 470
ENDGAME_HARD_DEADLINE = 500

# A9 early-game rush: first turns are a race for high-production neutrals.
EARLY_RUSH_END = 30
EARLY_RUSH_BONUS_PER_PROD = 5

# A7 minimum-fleet-for-speed: only bump tiny fleets for genuinely distant
# targets, so nearby-target ship counts (and the existing tests) are untouched.
SPEED_MIN_DISTANCE = 25.0
SPEED_MIN_ARRIVAL_TURNS = 20

# A10 preemptive defense: enemy economy within this range threatens a planet
# even with no fleet launched yet.
PREEMPTIVE_RANGE = 30.0

# A4 consolidation: backline planets holding more than this are dead weight.
CONSOLIDATE_MIN_SHIPS = 12

# A5 comets are production-1; not worth chasing for the last few turns.
COMET_MIN_REMAINING_LIFE = 10

# A3 coordination: only pool fleets that land within this many turns of each
# other (combat only combines fleets arriving on the same tick).
COORD_WINDOW = 3


# obs is dict -> returns value of attribute key (or default, if NONE)
# obs is object -> returns value of attribute element (or default, if NONE)
def _obs_get(obs, key, default=None):
    return obs.get(key, default) if isinstance(obs, dict) else getattr(obs, key, default)


# used if no decision made
def _empty_decision(runtime_ms=0.0, error=None):
    return {
        "agent_version": AGENT_VERSION,
        "runtime_ms": runtime_ms,
        "error": error,
        "candidates": [],
        "chosen_candidate_ids": [],
        "chosen_moves": [],  # kaggle return value
        "chosen_reason": "no legal production-scored targets",
        "economy": {},
    }


def _candidate_id(step, source_id, target_id, ships):
    return f"{AGENT_VERSION}:t{step}:p{source_id}->p{target_id}:{ships}"


def _reinforce_candidate_id(step, source_id, target_id, fleet_id, ships):
    return f"{AGENT_VERSION}:t{step}:p{source_id}->p{target_id}:f{fleet_id}:{ships}"


def _consolidate_candidate_id(step, source_id, target_id, ships):
    return f"{AGENT_VERSION}:t{step}:consolidate:p{source_id}->p{target_id}:{ships}"


def _game_phase(step):
    if step < EARLY_GAME_END:
        return "early"
    if step >= ENDGAME_START:
        return "endgame"
    if step >= LATE_GAME_START:
        return "late"
    return "mid"


def _ray_circle_first_distance(origin_x, origin_y, angle, center_x, center_y, radius):
    dx = math.cos(angle)
    dy = math.sin(angle)
    offset_x = origin_x - center_x
    offset_y = origin_y - center_y
    b = 2.0 * (offset_x * dx + offset_y * dy)
    c = offset_x * offset_x + offset_y * offset_y - radius * radius
    discriminant = b * b - 4.0 * c
    if discriminant < 0:
        return None
    root = math.sqrt(discriminant)
    first = (-b - root) / 2.0
    second = (-b + root) / 2.0
    if first >= 0:
        return first
    if second >= 0:
        return second
    return None


def _first_blocking_distance(fleet, target_planet, planets):
    target_distance = _ray_circle_first_distance(
        fleet.x,
        fleet.y,
        fleet.angle,
        target_planet.x,
        target_planet.y,
        target_planet.radius,
    )
    if target_distance is None:
        return None

    sun_distance = _ray_circle_first_distance(fleet.x, fleet.y, fleet.angle, 50.0, 50.0, 10.0)
    if sun_distance is not None and sun_distance < target_distance:
        return None

    for planet in planets:
        if planet.id == target_planet.id:
            continue
        blocking_distance = _ray_circle_first_distance(
            fleet.x,
            fleet.y,
            fleet.angle,
            planet.x,
            planet.y,
            planet.radius,
        )
        if blocking_distance is not None and blocking_distance < target_distance:
            return None

    return target_distance


# ---------------------------------------------------------------------------
# A6: Economy-aware strategy. Compute global production/ship balance and derive
# a strategic posture that biases expansion vs attack vs defense.
# ---------------------------------------------------------------------------
def _compute_economy(planets, fleets, player):
    my_production = my_ships = 0
    enemy_production = enemy_ships = 0
    neutral_production = 0
    per_opponent = {}
    for p in planets:
        if p.owner == player:
            my_production += p.production
            my_ships += p.ships
        elif p.owner == -1:
            neutral_production += p.production
        elif p.owner >= 0:
            enemy_production += p.production
            enemy_ships += p.ships
            stats = per_opponent.setdefault(p.owner, {"production": 0, "ships": 0})
            stats["production"] += p.production
            stats["ships"] += p.ships
    for f in fleets:
        if f.owner == player:
            my_ships += f.ships
        elif f.owner >= 0:
            enemy_ships += f.ships
            stats = per_opponent.setdefault(f.owner, {"production": 0, "ships": 0})
            stats["ships"] += f.ships

    leader = None
    if per_opponent:
        leader = max(per_opponent, key=lambda k: per_opponent[k]["production"])
    return {
        "my_production": my_production,
        "my_ships": my_ships,
        "enemy_production": enemy_production,
        "enemy_ships": enemy_ships,
        "neutral_production": neutral_production,
        "production_advantage": my_production - enemy_production,
        "ship_advantage": my_ships - enemy_ships,
        "num_opponents": len(per_opponent),
        "per_opponent": per_opponent,
        "leader": leader,
    }


def _strategic_posture(economy, step):
    """Return multiplicative weights (around 1.0) for expand / attack value.

    Ahead on production -> consolidate the lead: expand neutrals, defend, do not
    throw ships at fortified enemies. Behind -> press attacks on enemy economy.
    Lots of free neutral production on the board -> prioritise grabbing it.
    """
    advantage = economy["production_advantage"]
    expand_weight = 1.0
    attack_weight = 1.0

    if advantage > 5:
        expand_weight += 0.15
        attack_weight -= 0.25
    elif advantage < -3:
        attack_weight += 0.40
        expand_weight -= 0.10

    if economy["neutral_production"] > 10 and step < LATE_GAME_START:
        expand_weight += 0.20

    expand_weight = max(0.5, expand_weight)
    attack_weight = max(0.5, attack_weight)
    return {
        "expand_weight": expand_weight,
        "attack_weight": attack_weight,
        "production_advantage": advantage,
    }


# ---------------------------------------------------------------------------
# A2: Fleet-in-flight tracking. Count my own ships already heading to a target
# so we do not double-send and waste ships.
# ---------------------------------------------------------------------------
def _pending_arrivals(my_fleets, targets, planets):
    pending = {}
    for fleet in my_fleets:
        best_target = None
        best_distance = None
        for target in targets:
            distance = _first_blocking_distance(fleet, target, planets)
            if distance is None:
                continue
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_target = target
        if best_target is not None:
            pending[best_target.id] = pending.get(best_target.id, 0) + fleet.ships
    return pending


# ---------------------------------------------------------------------------
# A12: Enemy reinforcement awareness. If a fortified enemy planet sits within
# reach of our fleet's arrival, the capture will be contested.
# ---------------------------------------------------------------------------
def _enemy_reinforcement(target, enemy_planets, my_travel_turns):
    worst = 0
    for src in enemy_planets:
        if src.id == target.id:
            continue
        dist = geometry.distance_xy(src.x, src.y, target.x, target.y)
        enemy_travel = geometry.turns_to_reach(dist, max(1, src.ships))
        if enemy_travel <= my_travel_turns + 2 and src.ships > 10:
            worst = max(worst, src.ships)
    return worst


# A10: preemptive threat from nearby enemy economy (no launched fleet required).
def _preemptive_threat_score(my_planet, enemy_planets):
    threat = 0.0
    for enemy in enemy_planets:
        dist = geometry.distance_xy(my_planet.x, my_planet.y, enemy.x, enemy.y)
        if dist < PREEMPTIVE_RANGE:
            threat += enemy.ships / max(1.0, dist)
    return threat


# A12 / #12: positional value of a target -- planets near enemy economy are
# worth more to hold (frontline / chokepoint), all else equal.
def _positional_value(target, enemy_planets):
    frontline = 0.0
    for enemy in enemy_planets:
        dist = geometry.distance_xy(target.x, target.y, enemy.x, enemy.y)
        if dist < PREEMPTIVE_RANGE:
            frontline += 1.0
    return target.production * frontline * 2.0


def _detect_incoming_threats(enemy_fleets, my_planets, planets):
    threats = []
    for fleet in enemy_fleets:
        for target in my_planets:
            distance = _first_blocking_distance(fleet, target, planets)
            if distance is None:
                continue
            arrival_turns = geometry.turns_to_reach(distance, fleet.ships)
            projected_target_ships = target.ships + target.production * arrival_turns
            ships_needed = fleet.ships - projected_target_ships + 1
            if ships_needed <= 0:
                continue
            threats.append(
                {
                    "threat_id": f"fleet:{fleet.id}->planet:{target.id}",
                    "fleet": fleet,
                    "target": target,
                    "arrival_turns": arrival_turns,
                    "ships_needed": ships_needed,
                    "projected_target_ships": projected_target_ships,
                }
            )
    return threats


def _desired_reserve(source, step, score):
    phase = _game_phase(step)
    production = max(0, source.production)

    if phase == "early":
        return max(3, production)

    if phase == "mid":
        if production >= 5:
            return max(5, production)
        return max(3, production)

    # keep enough to prevent immediate flip if threat exists
    if phase == "endgame":
        if score > MIN_PROFITABLE_SCORE:
            return 1
        return max(1, production // 4)

    if score > MIN_PROFITABLE_SCORE:
        return max(1, production // 2)
    return max(3, production)


def _select_budgeted_candidates(source_candidates, source_budget=None):
    if not source_candidates:
        return []

    if source_budget is None:
        source_budget = source_candidates[0]["source_budget_before"]
    selected = []

    for candidate in sorted(source_candidates, key=lambda item: item["score"], reverse=True):
        candidate["source_budget_before"] = source_budget
        candidate["source_budget_after"] = source_budget - candidate["ships"]

        if not candidate["legal"]:
            continue

        if candidate["score"] <= MIN_PROFITABLE_SCORE:
            candidate["legal"] = False
            candidate["rejection_reason"] = "non_positive_score"
            continue

        if len(selected) >= MAX_MOVES_PER_SOURCE:
            candidate["legal"] = False
            candidate["rejection_reason"] = "source_budget_exhausted"
            continue

        if candidate["ships"] > source_budget:
            candidate["legal"] = False
            candidate["rejection_reason"] = "source_budget_exhausted"
            continue

        if source_budget - candidate["ships"] < candidate["desired_reserve"]:
            candidate["legal"] = False
            if source_budget <= candidate["desired_reserve"]:
                candidate["rejection_reason"] = "reserve_too_low"
            else:
                candidate["rejection_reason"] = "source_budget_exhausted"
            continue

        selected.append(candidate)
        source_budget -= candidate["ships"]
        candidate["source_budget_after"] = source_budget

    selected_ids = {candidate["candidate_id"] for candidate in selected}
    for candidate in source_candidates:
        if candidate["candidate_id"] not in selected_ids and candidate["legal"]:
            candidate["legal"] = False
            candidate["rejection_reason"] = "source_budget_exhausted"

    return selected


# ---------------------------------------------------------------------------
# A1 + A3: Global priority queue with multi-source coordination.
#
# Instead of greedy per-source selection, score every (source, target) pair,
# group by target, walk targets in value order, and pool ships from multiple
# sources onto one target when no single source can afford it alone.
# ---------------------------------------------------------------------------
def _allocation_rejection_reason(cand, source_budgets, moves_per_source, multi_source):
    """Mirror the per-source budgeter's reasoning for a rejected candidate."""
    sid = cand["source_planet_id"]
    budget = source_budgets.get(sid, 0)
    reserve = cand["desired_reserve"]
    if budget - reserve <= 0:
        return "reserve_too_low"
    if cand["ships"] > budget - reserve:
        return "coordination_insufficient" if multi_source else "source_budget_exhausted"
    return "source_budget_exhausted"


def _global_allocate(offense_candidates, source_budgets, step):
    """Allocate offense/expansion candidates globally by target priority.

    Mutates each candidate's legal/rejection_reason/source_budget_* fields and
    returns the ordered list of selected candidates (with the ships actually
    committed in candidate['ships']).
    """
    by_target = {}
    for cand in offense_candidates:
        by_target.setdefault(cand["target_planet_id"], []).append(cand)

    # Target priority = best achievable score on that target.
    target_priority = {}
    for target_id, cands in by_target.items():
        legal_scores = [c["score"] for c in cands if c["legal"] and c["score"] > MIN_PROFITABLE_SCORE]
        target_priority[target_id] = max(legal_scores) if legal_scores else float("-inf")

    moves_per_source = {sid: 0 for sid in source_budgets}
    selected = []

    for target_id in sorted(by_target, key=lambda t: target_priority[t], reverse=True):
        cands = by_target[target_id]
        # Viable per-source candidates for this target, closest (cheapest
        # timing) first so coordinated fleets arrive together.
        viable = [
            c for c in cands
            if c["legal"] and c["score"] > MIN_PROFITABLE_SCORE
        ]
        viable.sort(key=lambda c: (c["travel_turns"], -c["score"]))
        if not viable:
            continue

        # Net ships needed is defined by the closest contributor (it dictates
        # arrival timing and enemy production-during-travel).
        best = viable[0]
        net_need = best["ships"]
        sid0 = best["source_planet_id"]
        avail0 = source_budgets[sid0] - best["desired_reserve"]

        plan = []  # (candidate, ships_from_this_source)
        if avail0 >= net_need and moves_per_source[sid0] < MAX_MOVES_PER_SOURCE:
            # Common case: a single source can take the target outright.
            plan = [(best, net_need)]
        else:
            # A3 coordination. Fleets only combine in combat if they arrive on
            # the SAME tick, so restrict contributors to those landing within a
            # tight timing window, and inflate the requirement to cover the
            # garrison's production over that window plus a safety buffer.
            min_travel = best["travel_turns"]
            tgt_prod = max(0, best["score_components"].get("target_production", 0))
            contributors = [
                c for c in viable if c["travel_turns"] <= min_travel + COORD_WINDOW
            ]
            if len({c["source_planet_id"] for c in contributors}) >= 2:
                coord_need = net_need + tgt_prod * COORD_WINDOW + COORD_WINDOW
                remaining = coord_need
                for cand in contributors:
                    sid = cand["source_planet_id"]
                    if moves_per_source[sid] >= MAX_MOVES_PER_SOURCE:
                        continue
                    available = source_budgets[sid] - cand["desired_reserve"]
                    if available <= 0:
                        continue
                    send = min(available, remaining)
                    if send <= 0:
                        continue
                    plan.append((cand, send))
                    remaining -= send
                    if remaining <= 0:
                        break
                if remaining > 0:
                    plan = []  # cannot safely coordinate; do not waste ships

        if not plan:
            # Cannot capture even with coordination. Reason each viable
            # candidate the same way the per-source budgeter would: out of
            # reserve room vs simply out of budget; only flag a true
            # multi-source shortfall as coordination_insufficient.
            multi_source = len({c["source_planet_id"] for c in viable}) > 1
            for cand in viable:
                if not cand["legal"]:
                    continue
                cand["legal"] = False
                cand["rejection_reason"] = _allocation_rejection_reason(
                    cand, source_budgets, moves_per_source, multi_source
                )
            continue

        coordinated = len(plan) > 1
        for cand, send in plan:
            sid = cand["source_planet_id"]
            cand["source_budget_before"] = source_budgets[sid]
            cand["ships"] = send
            cand["move"] = [sid, cand["angle"], send]
            cand["coordinated"] = coordinated
            source_budgets[sid] -= send
            cand["source_budget_after"] = source_budgets[sid]
            moves_per_source[sid] += 1
            selected.append(cand)

        # Mark non-selected candidates for this target as superseded.
        chosen_ids = {c["candidate_id"] for c, _ in plan}
        for cand in cands:
            if cand["candidate_id"] not in chosen_ids and cand["legal"]:
                cand["legal"] = False
                cand["rejection_reason"] = _allocation_rejection_reason(
                    cand, source_budgets, moves_per_source, False
                )

    return selected


def _select_defense_candidates(defense_candidates, source_budgets):
    selected = []
    defended_threats = set()

    for candidate in sorted(defense_candidates, key=lambda item: item["score"], reverse=True):
        source_id = candidate["source_planet_id"]
        threat_key = (candidate["threat_fleet_id"], candidate["target_planet_id"])
        source_budget = source_budgets.get(source_id, 0)
        candidate["source_budget_before"] = source_budget
        candidate["source_budget_after"] = source_budget - candidate["ships"]

        if not candidate["legal"]:
            continue

        if threat_key in defended_threats:
            candidate["legal"] = False
            candidate["rejection_reason"] = "threat_already_defended"
            continue

        if candidate["ships"] > source_budget:
            candidate["legal"] = False
            candidate["rejection_reason"] = "source_budget_exhausted"
            continue

        if source_budget - candidate["ships"] < candidate["desired_reserve"]:
            candidate["legal"] = False
            if source_budget <= candidate["desired_reserve"]:
                candidate["rejection_reason"] = "reserve_too_low"
            else:
                candidate["rejection_reason"] = "source_budget_exhausted"
            continue

        selected.append(candidate)
        defended_threats.add(threat_key)
        source_budgets[source_id] = source_budget - candidate["ships"]
        candidate["source_budget_after"] = source_budgets[source_id]

    selected_ids = {candidate["candidate_id"] for candidate in selected}
    for candidate in defense_candidates:
        if candidate["candidate_id"] in selected_ids or not candidate["legal"]:
            continue
        threat_key = (candidate["threat_fleet_id"], candidate["target_planet_id"])
        if threat_key in defended_threats:
            candidate["legal"] = False
            candidate["rejection_reason"] = "threat_already_defended"
        else:
            candidate["legal"] = False
            candidate["rejection_reason"] = "source_budget_exhausted"

    return selected


# A9: early-game rush bonus for grabbing high-production neutrals fast.
def _early_game_bonus(step, target, travel_turns):
    if step > EARLY_RUSH_END or target.owner != -1:
        return 0
    arrival_step = step + travel_turns
    urgency = max(0, EARLY_RUSH_END - arrival_step)
    return urgency * max(0, target.production) * EARLY_RUSH_BONUS_PER_PROD


def _score_candidate(
    mine, target, step, ships_needed, distance, travel_turns, sun_blocked,
    orbit_trace, posture, enemy_planets,
):
    remaining_after_arrival = max(0, MAX_TURNS - step - travel_turns)
    source_reserve_after = mine.ships - ships_needed
    base_reserve = max(1, mine.production)
    base_reserve_penalty = max(0, base_reserve - source_reserve_after)
    production_value = target.production * remaining_after_arrival
    early_bonus = _early_game_bonus(step, target, travel_turns)
    positional_bonus = _positional_value(target, enemy_planets)
    economy_bonus = production_value * (posture["expand_weight"] - 1.0)
    ship_cost = ships_needed
    travel_cost = travel_turns
    strategic_value = production_value + early_bonus + positional_bonus + economy_bonus
    preliminary_score = strategic_value - ship_cost - travel_cost - base_reserve_penalty
    desired_reserve = _desired_reserve(mine, step, preliminary_score)
    reserve_penalty = max(0, desired_reserve - source_reserve_after)
    score = strategic_value - ship_cost - travel_cost - reserve_penalty
    score_components = {
        "production_value": production_value,
        "early_game_bonus": early_bonus,
        "endgame_bonus": 0,
        "positional_bonus": positional_bonus,
        "economy_bonus": economy_bonus,
        "expand_weight": posture["expand_weight"],
        "ship_cost": ship_cost,
        "travel_cost": travel_cost,
        "travel_turns": travel_turns,
        "sun_blocked": sun_blocked,
        "reserve_penalty": reserve_penalty,
        "desired_reserve": desired_reserve,
        "source_reserve_after": source_reserve_after,
        "remaining_after_arrival": remaining_after_arrival,
        "ships_needed": ships_needed,
        "target_ships": target.ships,
        "source_ships": mine.ships,
        "target_owner": target.owner,
        "target_production": target.production,
        "game_phase": _game_phase(step),
        "preliminary_score": preliminary_score,
        "base_reserve": base_reserve,
        **orbit_trace,
    }
    return score, score_components, desired_reserve


def _attack_margin(target):
    return max(2, target.production // 2 + 1)


def _attack_ships_needed(target, travel_turns):
    expected_production = max(0, target.production) * travel_turns
    return target.ships + expected_production + _attack_margin(target) + 1


def _attack_ships_and_travel(target, distance, initial_travel_turns):
    travel_turns = initial_travel_turns
    ships_needed = _attack_ships_needed(target, travel_turns)
    for _ in range(3):
        updated_travel_turns = geometry.turns_to_reach(distance, ships_needed)
        updated_ships_needed = _attack_ships_needed(target, updated_travel_turns)
        if updated_travel_turns == travel_turns and updated_ships_needed == ships_needed:
            break
        travel_turns = updated_travel_turns
        ships_needed = updated_ships_needed
    return ships_needed, travel_turns


def _score_attack_candidate(
    mine, target, step, ships_needed, distance, travel_turns, sun_blocked,
    orbit_trace, posture, enemy_planets, enemy_reinforce, focus_bonus,
):
    remaining_after_arrival = max(0, MAX_TURNS - step - travel_turns)
    source_reserve_after = mine.ships - ships_needed
    expected_production = max(0, target.production) * travel_turns
    margin = _attack_margin(target)
    base_reserve = max(1, mine.production)
    production_value = target.production * remaining_after_arrival
    enemy_denial_value = target.production * max(0, remaining_after_arrival // 2)
    weak_garrison_bonus = max(0, 20 - target.ships) * 10
    positional_bonus = _positional_value(target, enemy_planets)
    base_value = production_value + enemy_denial_value + weak_garrison_bonus
    economy_bonus = base_value * (posture["attack_weight"] - 1.0)
    # A12: contested captures lose value -- enemy reinforcements eat into the
    # margin and can flip the result back.
    reinforce_penalty = enemy_reinforce * 2
    ship_cost = ships_needed
    travel_cost = travel_turns * 2
    strategic_value = base_value + economy_bonus + positional_bonus + focus_bonus
    preliminary_score = strategic_value - ship_cost - travel_cost - reinforce_penalty
    desired_reserve = _desired_reserve(mine, step, preliminary_score)
    reserve_penalty = max(0, desired_reserve - source_reserve_after) * 2
    score = strategic_value - ship_cost - travel_cost - reserve_penalty - reinforce_penalty
    score_components = {
        "production_value": production_value,
        "enemy_denial_value": enemy_denial_value,
        "weak_garrison_bonus": weak_garrison_bonus,
        "positional_bonus": positional_bonus,
        "economy_bonus": economy_bonus,
        "focus_bonus": focus_bonus,
        "enemy_reinforce": enemy_reinforce,
        "reinforce_penalty": reinforce_penalty,
        "attack_weight": posture["attack_weight"],
        "endgame_bonus": 0,
        "ship_cost": ship_cost,
        "travel_cost": travel_cost,
        "travel_turns": travel_turns,
        "sun_blocked": sun_blocked,
        "reserve_penalty": reserve_penalty,
        "desired_reserve": desired_reserve,
        "source_reserve_after": source_reserve_after,
        "remaining_after_arrival": remaining_after_arrival,
        "ships_needed": ships_needed,
        "target_ships": target.ships,
        "source_ships": mine.ships,
        "target_owner": target.owner,
        "target_production": target.production,
        "expected_target_production_before_arrival": expected_production,
        "attack_margin": margin,
        "game_phase": _game_phase(step),
        "preliminary_score": preliminary_score,
        "base_reserve": base_reserve,
        **orbit_trace,
    }
    return score, score_components, desired_reserve


def _attack_overextends_source(mine, ships_needed, desired_reserve, step):
    if _game_phase(step) == "endgame":
        return False
    available_after_reserve = mine.ships - desired_reserve
    if available_after_reserve <= 0:
        return True
    if mine.production < 5:
        return False
    return ships_needed > available_after_reserve * 0.75


def _score_reinforce_candidate(source, threat, step, ships_needed, distance, travel_turns, sun_blocked):
    target = threat["target"]
    source_reserve_after = source.ships - ships_needed
    remaining_after_save = max(0, MAX_TURNS - step - threat["arrival_turns"])
    production_saved = target.production * remaining_after_save
    ships_saved = target.ships + threat["fleet"].ships
    preliminary_score = production_saved + ships_saved - ships_needed - travel_turns
    desired_reserve = _desired_reserve(source, step, preliminary_score)
    reserve_penalty = max(0, desired_reserve - source_reserve_after)
    lateness_penalty = max(0, travel_turns - threat["arrival_turns"]) * 100
    score = production_saved + ships_saved - ships_needed - travel_turns - lateness_penalty - reserve_penalty
    score_components = {
        "production_saved": production_saved,
        "ships_saved": ships_saved,
        "travel_cost": travel_turns,
        "travel_turns": travel_turns,
        "sun_blocked": sun_blocked,
        "reserve_penalty": reserve_penalty,
        "desired_reserve": desired_reserve,
        "source_reserve_after": source_reserve_after,
        "remaining_after_save": remaining_after_save,
        "ships_needed": ships_needed,
        "target_ships": target.ships,
        "source_ships": source.ships,
        "target_owner": target.owner,
        "target_production": target.production,
        "game_phase": _game_phase(step),
        "preliminary_score": preliminary_score,
        "projected_target_ships": threat["projected_target_ships"],
        "threat_arrival_turns": threat["arrival_turns"],
        "reinforcement_arrival_turns": travel_turns,
        "threat_fleet_ships": threat["fleet"].ships,
        "lateness_penalty": lateness_penalty,
    }
    return score, score_components, desired_reserve


def _generate_reinforce_candidates(threats, my_planets, step):
    candidates = []
    for threat in threats:
        target = threat["target"]
        ships_needed = threat["ships_needed"]
        for source in my_planets:
            if source.id == target.id:
                continue
            distance = geometry.distance_xy(source.x, source.y, target.x, target.y)
            angle = geometry.angle_to_xy(source.x, source.y, target.x, target.y)
            travel_turns = geometry.turns_to_reach(distance, ships_needed)
            sun_blocked = geometry.shot_hits_sun((source.x, source.y), (target.x, target.y))
            score, score_components, desired_reserve = _score_reinforce_candidate(
                source,
                threat,
                step,
                ships_needed,
                distance,
                travel_turns,
                sun_blocked,
            )
            source_reserve_after = source.ships - ships_needed
            affordable = source.ships >= ships_needed
            timely = travel_turns <= threat["arrival_turns"]
            reserve_ok = source_reserve_after >= desired_reserve
            legal = (
                not sun_blocked
                and timely
                and affordable
                and reserve_ok
                and score > MIN_PROFITABLE_SCORE
            )
            if sun_blocked:
                rejection_reason = "reinforcement_sun_blocked"
            elif not timely:
                rejection_reason = "reinforcement_too_late"
            elif not reserve_ok:
                rejection_reason = "reserve_too_low"
            elif not affordable:
                rejection_reason = "insufficient_source_ships"
            elif score <= MIN_PROFITABLE_SCORE:
                rejection_reason = "non_positive_score"
            else:
                rejection_reason = None
            candidates.append(
                {
                    "candidate_id": _reinforce_candidate_id(step, source.id, target.id, threat["fleet"].id, ships_needed),
                    "candidate_type": "reinforce",
                    "move": [source.id, angle, ships_needed],
                    "source_planet_id": source.id,
                    "target_planet_id": target.id,
                    "threat_fleet_id": threat["fleet"].id,
                    "threat_arrival_turns": threat["arrival_turns"],
                    "reinforcement_arrival_turns": travel_turns,
                    "ships_needed": ships_needed,
                    "ships": ships_needed,
                    "angle": angle,
                    "distance": distance,
                    "travel_turns": travel_turns,
                    "score": score,
                    "score_components": score_components,
                    "source_budget_before": source.ships,
                    "source_budget_after": source.ships - ships_needed,
                    "desired_reserve": desired_reserve,
                    "legal": legal,
                    "rejection_reason": rejection_reason,
                    "reason": "highest value defensive reinforcement",
                }
            )
    return candidates


# A4: consolidation -- move idle ships off low-value backline planets toward
# the frontline so they actually fight instead of sitting forever.
def _identify_frontline(my_planets, enemy_planets):
    if not enemy_planets:
        return set()
    frontline = set()
    for mine in my_planets:
        nearest = min(
            geometry.distance_xy(mine.x, mine.y, e.x, e.y) for e in enemy_planets
        )
        frontline.add((mine.id, nearest))
    if not frontline:
        return set()
    # Frontline = the closer half of our planets to the enemy.
    ordered = sorted(frontline, key=lambda item: item[1])
    cutoff = max(1, len(ordered) // 2)
    return {pid for pid, _ in ordered[:cutoff]}


def _generate_consolidation_candidates(my_planets, enemy_planets, planets, step, source_budgets):
    candidates = []
    if len(my_planets) < 2 or not enemy_planets:
        return candidates
    frontline_ids = _identify_frontline(my_planets, enemy_planets)
    frontline_planets = [p for p in my_planets if p.id in frontline_ids]
    if not frontline_planets:
        return candidates
    backline = [
        p for p in my_planets
        if p.id not in frontline_ids and source_budgets.get(p.id, 0) > CONSOLIDATE_MIN_SHIPS
    ]
    for source in backline:
        budget = source_budgets.get(source.id, 0)
        keep = max(2, source.production)
        ships_to_send = budget - keep
        if ships_to_send <= 0:
            continue
        # Send toward the nearest frontline planet that is not sun-blocked.
        best = None
        for target in frontline_planets:
            if target.id == source.id:
                continue
            if geometry.shot_hits_sun((source.x, source.y), (target.x, target.y)):
                continue
            dist = geometry.distance_xy(source.x, source.y, target.x, target.y)
            if best is None or dist < best[1]:
                best = (target, dist)
        if best is None:
            continue
        target, distance = best
        angle = geometry.angle_to_xy(source.x, source.y, target.x, target.y)
        travel_turns = geometry.turns_to_reach(distance, ships_to_send)
        # Low positive score: useful but never preempts real expansion/attacks.
        score = ships_to_send * 0.5 - travel_turns
        legal = score > MIN_PROFITABLE_SCORE
        candidates.append(
            {
                "candidate_id": _consolidate_candidate_id(step, source.id, target.id, ships_to_send),
                "candidate_type": "consolidate",
                "move": [source.id, angle, ships_to_send],
                "source_planet_id": source.id,
                "target_planet_id": target.id,
                "ships": ships_to_send,
                "angle": angle,
                "distance": distance,
                "travel_turns": travel_turns,
                "score": score,
                "score_components": {
                    "ships_moved": ships_to_send,
                    "travel_turns": travel_turns,
                    "game_phase": _game_phase(step),
                },
                "source_budget_before": budget,
                "source_budget_after": budget - ships_to_send,
                "desired_reserve": keep,
                "legal": legal,
                "rejection_reason": None if legal else "non_positive_score",
                "reason": "move idle backline ships to the frontline",
            }
        )
    return candidates


def _attack_can_arrive(step, travel_turns):
    return step + travel_turns < ENDGAME_HARD_DEADLINE


def _endgame_capture_risk(mine, enemy_fleets):
    for fleet in enemy_fleets:
        dist = geometry.distance_xy(fleet.x, fleet.y, mine.x, mine.y)
        if geometry.turns_to_reach(dist, fleet.ships) <= 1:
            return True
    return False


# ---------------------------------------------------------------------------
# A5 / comets: read comet path data to estimate remaining lifetime so we only
# chase a comet we can actually reach and hold profitably.
# ---------------------------------------------------------------------------
def _comet_remaining_life(comet_id, comets_data):
    for group in comets_data or []:
        ids = group.get("planet_ids", []) if isinstance(group, dict) else []
        if comet_id not in ids:
            continue
        i = ids.index(comet_id)
        paths = group.get("paths", [])
        path_index = group.get("path_index", 0)
        if i < len(paths):
            return max(0, len(paths[i]) - max(0, path_index) - 1)
    return None


def decide_with_trace(obs):
    started = time.perf_counter()
    decision = _empty_decision()
    moves = []

    try:
        step = _obs_get(obs, "step", 0) or 0
        player = _obs_get(obs, "player", 0)
        raw_planets = _obs_get(obs, "planets", [])
        raw_fleets = _obs_get(obs, "fleets", [])
        angular_velocity = _obs_get(obs, "angular_velocity", 0)
        raw_initial_planets = _obs_get(obs, "initial_planets", None)
        comet_ids = set(_obs_get(obs, "comet_planet_ids", []) or [])
        comets_data = _obs_get(obs, "comets", []) or []

        # Parse into named tuples for readable field access:
        #   Planet(id, owner, x, y, radius, ships, production)
        #   owner == -1 means neutral, 0-3 are player IDs
        planets = [Planet(*p) for p in raw_planets]
        fleets = [Fleet(*f) for f in raw_fleets]
        initial_planets = [Planet(*p) for p in (raw_initial_planets or [])]
        initial_by_id = prediction.planet_by_id(initial_planets)
        my_planets = [p for p in planets if p.owner == player]
        my_fleets = [f for f in fleets if f.owner == player]
        enemy_fleets = [f for f in fleets if f.owner != player and f.owner >= 0]
        enemy_planets = [p for p in planets if p.owner >= 0 and p.owner != player]
        targets = [p for p in planets if p.owner != player]
        source_budgets = {planet.id: planet.ships for planet in my_planets}

        # A6: economy + strategic posture.
        economy = _compute_economy(planets, fleets, player)
        posture = _strategic_posture(economy, step)
        decision["economy"] = economy
        decision["posture"] = posture

        # A11: in 4-player games, prefer attacking the leader; never bully the
        # weakest while the leader snowballs. Neutrals are always fair game.
        focus_owner = None
        if economy["num_opponents"] > 1:
            focus_owner = economy["leader"]

        # A2: ships already in flight toward each target.
        pending = _pending_arrivals(my_fleets, targets, planets)

        # Defense first (safety): selected reinforcements reserve their ships
        # before any offense is allocated.
        threats = _detect_incoming_threats(enemy_fleets, my_planets, planets)
        defense_candidates = _generate_reinforce_candidates(threats, my_planets, step)
        selected_defenses = _select_defense_candidates(defense_candidates, source_budgets)
        selected_defense_ids = {candidate["candidate_id"] for candidate in selected_defenses}
        for candidate in defense_candidates:
            if candidate["candidate_id"] in selected_defense_ids:
                moves.append(candidate["move"])
                decision["chosen_candidate_ids"].append(candidate["candidate_id"])
            decision["candidates"].append(candidate)

        if not targets and not defense_candidates:
            decision["chosen_moves"] = moves
            if moves:
                decision["chosen_reason"] = "selected defensive reinforcements"
            decision["runtime_ms"] = (time.perf_counter() - started) * 1000
            return {"moves": moves, "decision": decision}

        # Build the global offense/expansion/comet candidate pool from ALL
        # sources, so allocation can choose the globally best targets (A1).
        offense_candidates = []
        for mine in my_planets:
            for target in targets:
                is_attack = target.owner >= 0
                is_comet = target.id in comet_ids

                # A11: skip non-leader enemies in 4p (still allow neutrals/comets).
                if is_attack and focus_owner is not None and target.owner != focus_owner:
                    continue

                base_ships_needed = target.ships + 1
                static_distance = geometry.distance_xy(mine.x, mine.y, target.x, target.y)
                static_travel_turns = geometry.turns_to_reach(static_distance, base_ships_needed)
                if is_attack:
                    base_ships_needed, static_travel_turns = _attack_ships_and_travel(
                        target, static_distance, static_travel_turns,
                    )

                target_is_orbiting = raw_initial_planets is not None and prediction.is_orbiting_planet(target)
                used_initial_planet = target.id in initial_by_id
                orbit_trace = {
                    "target_is_orbiting": target_is_orbiting,
                    "intercept_turn": None,
                    "timing_error": None,
                    "predicted_target_x": target.x,
                    "predicted_target_y": target.y,
                    "used_initial_planet": False,
                }

                ships_needed = base_ships_needed
                orbit_rejection_reason = None
                if target_is_orbiting:
                    initial_target = initial_by_id.get(target.id, target)
                    intercept = prediction.sample_orbit_intercept(
                        mine,
                        target,
                        initial_target,
                        angular_velocity,
                        ships_needed,
                        current_step=step,  # A8: predict at step + future_turn
                    )
                    if intercept is None:
                        distance = static_distance
                        angle = geometry.angle_to_xy(mine.x, mine.y, target.x, target.y)
                        travel_turns = static_travel_turns
                        sun_blocked = geometry.shot_hits_sun((mine.x, mine.y), (target.x, target.y))
                        orbit_rejection_reason = "no_orbit_intercept"
                    else:
                        predicted_x, predicted_y = intercept["predicted_target"]
                        distance = intercept["distance"]
                        travel_turns = intercept["travel_turns"]
                        angle = intercept["angle"]
                        sun_blocked = intercept["sun_blocked"]
                        orbit_rejection_reason = "orbit_intercept_sun_blocked" if sun_blocked else None
                        orbit_trace.update(
                            {
                                "intercept_turn": intercept["intercept_turn"],
                                "timing_error": intercept["timing_error"],
                                "predicted_target_x": predicted_x,
                                "predicted_target_y": predicted_y,
                                "used_initial_planet": used_initial_planet,
                            }
                        )
                else:
                    distance = static_distance
                    angle = geometry.angle_to_xy(mine.x, mine.y, target.x, target.y)
                    travel_turns = static_travel_turns
                    sun_blocked = geometry.shot_hits_sun((mine.x, mine.y), (target.x, target.y))

                if is_attack:
                    ships_needed, travel_turns = _attack_ships_and_travel(target, distance, travel_turns)
                    if not target_is_orbiting:
                        angle = geometry.angle_to_xy(mine.x, mine.y, target.x, target.y)

                # A2: account for ships already in flight. Fleets launched on
                # DIFFERENT turns arrive on different ticks and do NOT combine
                # in combat (only same-tick arrivals merge). Subtracting their
                # ships from ships_needed made the agent dribble fleets too
                # small to win -- each lost its fight and the target never fell.
                # Instead: only treat a target as handled when in-flight ships
                # already fully cover the requirement; otherwise keep the full
                # requirement and require a single decisive launch (the source
                # waits and accumulates rather than dribbling).
                already_sent = pending.get(target.id, 0)
                already_covered = already_sent >= ships_needed

                # A7: enforce a minimum fleet size for distant targets so the
                # fleet does not crawl. Only kicks in past SPEED_MIN_DISTANCE,
                # leaving nearby-target ship counts unchanged.
                speed_minimum = 0
                if distance > SPEED_MIN_DISTANCE and not sun_blocked:
                    speed_minimum = geometry.min_ships_for_arrival(distance, SPEED_MIN_ARRIVAL_TURNS)
                    if speed_minimum > ships_needed:
                        ships_needed = speed_minimum
                        travel_turns = geometry.turns_to_reach(distance, ships_needed)

                # A12: will the enemy reinforce this target before we arrive?
                enemy_reinforce = 0
                if is_attack:
                    enemy_reinforce = _enemy_reinforcement(target, enemy_planets, travel_turns)

                # A11: focus-fire bonus on the leader in 4p games.
                focus_bonus = 0
                if is_attack and focus_owner is not None and target.owner == focus_owner:
                    focus_bonus = target.production * max(0, MAX_TURNS - step) // 4

                move = [mine.id, angle, ships_needed]
                if is_attack:
                    score, score_components, desired_reserve = _score_attack_candidate(
                        mine, target, step, ships_needed, distance, travel_turns,
                        sun_blocked, orbit_trace, posture, enemy_planets,
                        enemy_reinforce, focus_bonus,
                    )
                else:
                    score, score_components, desired_reserve = _score_candidate(
                        mine, target, step, ships_needed, distance, travel_turns,
                        sun_blocked, orbit_trace, posture, enemy_planets,
                    )

                if is_comet:
                    remaining_life = _comet_remaining_life(target.id, comets_data)
                    score_components["comet_remaining_life"] = remaining_life
                    if remaining_life is not None and (
                        remaining_life < COMET_MIN_REMAINING_LIFE
                        or travel_turns >= remaining_life
                    ):
                        score = MIN_PROFITABLE_SCORE - 1  # not worth chasing

                source_reserve_after = mine.ships - ships_needed

                if _game_phase(step) == "endgame" and _endgame_capture_risk(mine, enemy_fleets):
                    desired_reserve = max(desired_reserve, mine.ships // 2)

                affordable = mine.ships >= ships_needed
                reserve_ok = source_reserve_after >= desired_reserve
                attack_overextended = (
                    is_attack
                    and affordable
                    and reserve_ok
                    and _attack_overextends_source(mine, ships_needed, desired_reserve, step)
                )
                endgame_unreachable = (
                    _game_phase(step) == "endgame"
                    and is_attack
                    and not _attack_can_arrive(step, travel_turns)
                )
                legal = (
                    affordable
                    and reserve_ok
                    and not attack_overextended
                    and not sun_blocked
                    and not already_covered
                    and orbit_rejection_reason is None
                    and not endgame_unreachable
                    and score > MIN_PROFITABLE_SCORE
                )
                if orbit_rejection_reason is not None:
                    rejection_reason = orbit_rejection_reason
                elif sun_blocked:
                    rejection_reason = "sun_blocked"
                elif already_covered:
                    rejection_reason = "already_inflight"
                elif endgame_unreachable:
                    rejection_reason = "endgame_unreachable"
                elif not affordable:
                    rejection_reason = "insufficient_source_ships"
                elif not reserve_ok:
                    rejection_reason = "reserve_too_low"
                elif attack_overextended:
                    rejection_reason = "attack_overextension"
                elif score <= MIN_PROFITABLE_SCORE:
                    rejection_reason = "non_positive_score"
                else:
                    rejection_reason = None

                candidate_type = "comet" if is_comet else ("attack" if is_attack else "expand")
                reason = (
                    "free comet economy" if is_comet
                    else "opportunistic attack score" if is_attack
                    else "highest production-adjusted expansion score"
                )
                offense_candidates.append(
                    {
                        "candidate_id": _candidate_id(step, mine.id, target.id, ships_needed),
                        "candidate_type": candidate_type,
                        "move": move,
                        "source_planet_id": mine.id,
                        "target_planet_id": target.id,
                        "ships": ships_needed,
                        "ships_needed": ships_needed,
                        "angle": angle,
                        "distance": distance,
                        "travel_turns": travel_turns,
                        "score": score,
                        "score_components": score_components,
                        "source_budget_before": source_budgets[mine.id],
                        "source_budget_after": source_budgets[mine.id] - ships_needed,
                        "desired_reserve": desired_reserve,
                        "legal": legal,
                        "rejection_reason": rejection_reason,
                        "coordinated": False,
                        "reason": reason,
                    }
                )

        # A1 + A3: global allocation across all sources with coordination.
        selected_offense = _global_allocate(offense_candidates, source_budgets, step)
        selected_offense_ids = {c["candidate_id"] for c in selected_offense}

        # A4: consolidation uses whatever budget remains after offense.
        consolidation_candidates = _generate_consolidation_candidates(
            my_planets, enemy_planets, planets, step, source_budgets
        )
        selected_consolidation = _global_allocate(consolidation_candidates, source_budgets, step)
        selected_consolidation_ids = {c["candidate_id"] for c in selected_consolidation}

        # Emit moves in priority order: offense first, then consolidation.
        for candidate in selected_offense:
            moves.append(candidate["move"])
            decision["chosen_candidate_ids"].append(candidate["candidate_id"])
        for candidate in selected_consolidation:
            moves.append(candidate["move"])
            decision["chosen_candidate_ids"].append(candidate["candidate_id"])

        for candidate in offense_candidates:
            decision["candidates"].append(candidate)
        for candidate in consolidation_candidates:
            decision["candidates"].append(candidate)

        decision["chosen_moves"] = moves
        offense_count = len(selected_offense) + len(selected_consolidation)
        if selected_defenses and offense_count:
            decision["chosen_reason"] = "selected defensive and production-scored legal targets"
        elif selected_defenses:
            decision["chosen_reason"] = "selected defensive reinforcements"
        elif moves:
            decision["chosen_reason"] = "selected budgeted production-scored legal targets"

    except Exception as exc:  # Kaggle expects the agent wrapper to survive local trace failures.
        decision["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        moves = []
        decision["chosen_moves"] = moves
        decision["chosen_candidate_ids"] = []
    finally:
        decision["runtime_ms"] = (time.perf_counter() - started) * 1000

    return {"moves": moves, "decision": decision}


def agent(obs):
    return decide_with_trace(obs)["moves"]
