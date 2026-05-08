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

try:
    from kaggle_environments.envs.orbit_wars.orbit_wars import Planet
except ModuleNotFoundError:
    Planet = namedtuple("Planet", "id owner x y radius ships production")


AGENT_VERSION = "nearest_sniper_v2_traceable"

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


def decide_with_trace(obs):
    started = time.perf_counter()
    decision = _empty_decision()
    moves = []

    try:
        step = 0
        player = _obs_get(obs, "player", 0)
        raw_planets = _obs_get(obs, "planets", [])
        angular_velocity = _obs_get(obs, "angular_velocity", 0)

        # Parse into named tuples for readable field access:
        #   Planet(id, owner, x, y, radius, ships, production)
        #   owner == -1 means neutral, 0-3 are player IDs
        planets = [Planet(*p) for p in raw_planets]
        my_planets = [p for p in planets if p.owner == player]
        targets = [p for p in planets if p.owner != player]
        
        source_budget = { p.id: max(0, p.ships - required_reserve(step, p)) for p in my_planets }

        # case - no enemies
        if not targets:
            return {"moves": moves, "decision": decision}

        for mine in my_planets:
            source_candidates = []
            for target in targets:
                
                ships_needed = target.ships + 1
                
                LIMIT = 15 # change later if necessary
                TIME_THRESHOLD = 2.0 # change later if necessary
                
                best_sample = None
                best_error = float("inf")
                
                if geometry.is_orbiting(target):
                    for t in range (1, LIMIT + 1):
                        theta = geometry.angle_to_xy(target.x, target.y, 50, 50)

                        pred_x, pred_y = geometry.predict_position(target.radius, theta, angular_velocity, t)

                        distance = geometry.distance_xy(mine.x, mine.y, pred_x, pred_y)
                        travel_turns = geometry.turns_to_reach(distance, ships_needed)
                        timing_error = abs(travel_turns - t)
                        
                        if geometry.shot_hits_sun((mine.x, mine.y), (pred_x, pred_y)):
                            continue
                        
                        if timing_error < best_error:
                            best_error = timing_error
                            best_sample = {
                                "distance": distance,
                                "travel_turns": travel_turns,
                                "ships_needed": ships_needed,
                                "angle": geometry.angle_to_xy(mine.x, mine.y, pred_x, pred_y),
                            }
                        
                    if best_sample is None or best_error > TIME_THRESHOLD:
                        continue

                    distance = best_sample["distance"]
                    travel_turns = best_sample["travel_turns"]
                    ships_needed = best_sample["ships_needed"]
                    angle = best_sample["angle"]
                    
                else:
                    distance = geometry.distance_xy(mine.x, mine.y, target.x, target.y)
                    angle = geometry.angle_to_xy(mine.x, mine.y, target.x, target.y)
                    travel_turns = geometry.turns_to_reach(distance, ships_needed)
                
                move = [mine.id, angle, ships_needed]
                remaining_after_arrival = max(0, 500 - step - travel_turns)
                source_reserve_after = mine.ships - ships_needed
                desired_reserve = mine.production
                reserve_penalty = max(0, desired_reserve - source_reserve_after)
                production_value = target.production * remaining_after_arrival
                ship_cost = ships_needed
                travel_cost = travel_turns
                score = production_value - ship_cost - travel_cost - reserve_penalty
                affordable = mine.ships >= ships_needed
                reserve_ok = source_reserve_after >= desired_reserve
                sun_blocked = geometry.shot_hits_sun((mine.x, mine.y), (target.x, target.y))
                legal = affordable and reserve_ok and not sun_blocked
                if sun_blocked:
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
                    "score_components": {
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
                    },
                    "legal": legal,
                    "rejection_reason": rejection_reason,
                    "reason": "highest production-adjusted expansion score",
                }
                source_candidates.append(candidate)

            legal_candidates = [candidate for candidate in source_candidates if candidate["legal"]]
            
            legal_candidates.sort(key=lambda c: c["score"], reverse=True)
            
            for candidate in legal_candidates:
                src = candidate["source_planet_id"]
                cost = candidate["ships"]

                if source_budget[src] >= cost:
                    moves.append(candidate["move"])
                    decision["chosen_candidate_ids"].append(candidate["candidate_id"])
                    source_budget[src] -= cost
            
        decision["chosen_moves"] = moves
        if moves:
            decision["chosen_reason"] = "selected highest-scoring legal production target per owned planet"

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
