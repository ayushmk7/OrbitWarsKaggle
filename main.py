"""
Orbit Wars - Nearest Planet Sniper Agent

A simple agent that captures the nearest unowned planet when it has
enough ships to guarantee the takeover.

Strategy:
  For each planet we own, score planets we don't own by production value,
  travel time, capture cost, and source reserve after launch.

Key concepts demonstrated:
  - Parsing the observation (planets, player ID)
  - Computing angles with atan2 for fleet direction
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


def _obs_get(obs, key, default=None):
    return obs.get(key, default) if isinstance(obs, dict) else getattr(obs, key, default)


def _empty_decision(runtime_ms=0.0, error=None):
    return {
        "agent_version": AGENT_VERSION,
        "runtime_ms": runtime_ms,
        "error": error,
        "candidates": [],
        "chosen_candidate_ids": [],
        "chosen_moves": [],
        "chosen_reason": "no legal production-scored targets",
    }


def _candidate_id(step, source_id, target_id, ships):
    return f"{AGENT_VERSION}:t{step}:p{source_id}->p{target_id}:{ships}"


def decide_with_trace(obs):
    started = time.perf_counter()
    decision = _empty_decision()
    moves = []

    try:
        step = _obs_get(obs, "step", 0)
        player = _obs_get(obs, "player", 0)
        raw_planets = _obs_get(obs, "planets", [])

        # Parse into named tuples for readable field access:
        #   Planet(id, owner, x, y, radius, ships, production)
        #   owner == -1 means neutral, 0-3 are player IDs
        planets = [Planet(*p) for p in raw_planets]
        my_planets = [p for p in planets if p.owner == player]
        targets = [p for p in planets if p.owner != player]

        if not targets:
            return {"moves": moves, "decision": decision}

        for mine in my_planets:
            source_candidates = []
            for target in targets:
                distance = geometry.distance_xy(mine.x, mine.y, target.x, target.y)
                ships_needed = target.ships + 1
                angle = geometry.angle_to_xy(mine.x, mine.y, target.x, target.y)
                move = [mine.id, angle, ships_needed]
                travel_turns = geometry.turns_to_reach(distance, ships_needed)
                remaining_after_arrival = max(0, 500 - step - travel_turns)
                source_reserve_after = mine.ships - ships_needed
                desired_reserve = max(1, mine.production)
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
            best = max(legal_candidates, key=lambda candidate: candidate["score"], default=None)
            for candidate in source_candidates:
                if best is not None and candidate["candidate_id"] == best["candidate_id"]:
                    moves.append(candidate["move"])
                    decision["chosen_candidate_ids"].append(candidate["candidate_id"])
                elif candidate["legal"]:
                    candidate["rejection_reason"] = "not_highest_scoring_target_for_source"
                decision["candidates"].append(candidate)

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
