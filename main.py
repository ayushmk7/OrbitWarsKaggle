"""
Orbit Wars - Production-Scored Expansion Agent

A traceable rule-based agent that scores unowned planets by production value,
travel time, capture cost, source reserve, and sun safety.

Strategy:
  For each planet we own, evaluate planets we don't own and choose the
  highest-scoring legal target.

Key concepts demonstrated:
  - Parsing the observation (planets, player ID)
  - Computing angles for fleet direction
  - Rejecting sun-blocked launches before selection
  - Sending moves as [from_planet_id, angle, num_ships]
"""

import time
from collections import namedtuple
import geometry
import prediction

try:
    from kaggle_environments.envs.orbit_wars.orbit_wars import Planet
except ModuleNotFoundError:
    Planet = namedtuple("Planet", "id owner x y radius ships production")


AGENT_VERSION = "nearest_sniper_v2_traceable"
MAX_TURNS = 500
EARLY_GAME_END = 150
LATE_GAME_START = 400
MIN_PROFITABLE_SCORE = 0
MAX_MOVES_PER_SOURCE = 2

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
        "chosen_moves": [], # kaggle return value
        "chosen_reason": "no legal production-scored targets",
    }


def _candidate_id(step, source_id, target_id, ships):
    return f"{AGENT_VERSION}:t{step}:p{source_id}->p{target_id}:{ships}"


def _game_phase(step):
    if step < EARLY_GAME_END:
        return "early"
    if step >= LATE_GAME_START:
        return "late"
    return "mid"

def _desired_reserve(source, step, score):
    phase = _game_phase(step)
    production = max(0, source.production)

    if phase == "early":
        return max(3, production)

    if phase == "mid":
        if production >= 5:
            return max(5, production)
        return max(3, production)

    if score > MIN_PROFITABLE_SCORE:
        return max(1, production // 2)
    return max(3, production)


def _select_budgeted_candidates(source_candidates):
    if not source_candidates:
        return []

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


def _score_candidate(mine, target, step, ships_needed, distance, travel_turns, sun_blocked, orbit_trace):
    remaining_after_arrival = max(0, MAX_TURNS - step - travel_turns)
    source_reserve_after = mine.ships - ships_needed
    base_reserve = max(1, mine.production)
    base_reserve_penalty = max(0, base_reserve - source_reserve_after)
    production_value = target.production * remaining_after_arrival
    ship_cost = ships_needed
    travel_cost = travel_turns
    preliminary_score = production_value - ship_cost - travel_cost - base_reserve_penalty
    desired_reserve = _desired_reserve(mine, step, preliminary_score)
    reserve_penalty = max(0, desired_reserve - source_reserve_after)
    score = production_value - ship_cost - travel_cost - reserve_penalty
    score_components = {
        "production_value": production_value,
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


def decide_with_trace(obs):
    started = time.perf_counter()
    decision = _empty_decision()
    moves = []

    try:
        step = _obs_get(obs, "step", 0) or 0
        player = _obs_get(obs, "player", 0)
        raw_planets = _obs_get(obs, "planets", [])
        angular_velocity = _obs_get(obs, "angular_velocity", 0)
        raw_initial_planets = _obs_get(obs, "initial_planets", None)

        # Parse into named tuples for readable field access:
        #   Planet(id, owner, x, y, radius, ships, production)
        #   owner == -1 means neutral, 0-3 are player IDs
        planets = [Planet(*p) for p in raw_planets]
        initial_planets = [Planet(*p) for p in (raw_initial_planets or [])]
        initial_by_id = prediction.planet_by_id(initial_planets)
        my_planets = [p for p in planets if p.owner == player]
        targets = [p for p in planets if p.owner != player]

        # case - no enemies
        if not targets:
            return {"moves": moves, "decision": decision}

        for mine in my_planets:
            source_candidates = []
            for target in targets:
                
                ships_needed = target.ships + 1
                
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

                orbit_rejection_reason = None
                if target_is_orbiting:
                    initial_target = initial_by_id.get(target.id, target)
                    intercept = prediction.sample_orbit_intercept(
                        mine,
                        target,
                        initial_target,
                        angular_velocity,
                        ships_needed,
                    )
                    if intercept is None:
                        distance = geometry.distance_xy(mine.x, mine.y, target.x, target.y)
                        angle = geometry.angle_to_xy(mine.x, mine.y, target.x, target.y)
                        travel_turns = geometry.turns_to_reach(distance, ships_needed)
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
                    distance = geometry.distance_xy(mine.x, mine.y, target.x, target.y)
                    angle = geometry.angle_to_xy(mine.x, mine.y, target.x, target.y)
                    travel_turns = geometry.turns_to_reach(distance, ships_needed)
                    sun_blocked = geometry.shot_hits_sun((mine.x, mine.y), (target.x, target.y))
                
                move = [mine.id, angle, ships_needed]
                score, score_components, desired_reserve = _score_candidate(
                    mine,
                    target,
                    step,
                    ships_needed,
                    distance,
                    travel_turns,
                    sun_blocked,
                    orbit_trace,
                )
                source_reserve_after = mine.ships - ships_needed
                affordable = mine.ships >= ships_needed
                reserve_ok = source_reserve_after >= desired_reserve
                legal = affordable and reserve_ok and not sun_blocked and orbit_rejection_reason is None
                if orbit_rejection_reason is not None:
                    rejection_reason = orbit_rejection_reason
                elif sun_blocked:
                    rejection_reason = "sun_blocked"
                elif not affordable:
                    rejection_reason = "insufficient_source_ships"
                elif not reserve_ok:
                    rejection_reason = "reserve_too_low"
                else:
                    rejection_reason = None
                candidate = {
                    "candidate_id": _candidate_id(step, mine.id, target.id, ships_needed),
                    "candidate_type": "attack" if target.owner >= 0 else "expand",
                    "move": move,
                    "source_planet_id": mine.id,
                    "target_planet_id": target.id,
                    "ships": ships_needed,
                    "angle": angle,
                    "distance": distance,
                    "travel_turns": travel_turns,
                    "score": score,
                    "score_components": score_components,
                    "source_budget_before": mine.ships,
                    "source_budget_after": mine.ships - ships_needed,
                    "desired_reserve": desired_reserve,
                    "legal": legal,
                    "rejection_reason": rejection_reason,
                    "reason": "highest production-adjusted expansion score",
                }
                source_candidates.append(candidate)

            selected = _select_budgeted_candidates(source_candidates)
            selected_ids = {candidate["candidate_id"] for candidate in selected}
            for candidate in source_candidates:
                if candidate["candidate_id"] in selected_ids:
                    moves.append(candidate["move"])
                    decision["chosen_candidate_ids"].append(candidate["candidate_id"])
                decision["candidates"].append(candidate)
            
        decision["chosen_moves"] = moves
        if moves:
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
