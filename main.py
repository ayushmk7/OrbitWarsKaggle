"""
Orbit Wars - Nearest Planet Sniper Agent

A simple agent that captures the nearest unowned planet when it has
enough ships to guarantee the takeover.

Strategy:
  For each planet we own, find the closest planet we don't own.
  If we have more ships than the target's garrison, send exactly
  enough to capture it (garrison + 1). Otherwise, wait and accumulate.

Key concepts demonstrated:
  - Parsing the observation (planets, player ID)
  - Computing angles with atan2 for fleet direction
  - Sending moves as [from_planet_id, angle, num_ships]
"""

import math
import time
from collections import namedtuple

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
        "chosen_reason": "no legal nearest capturable targets",
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
                distance = math.sqrt((mine.x - target.x) ** 2 + (mine.y - target.y) ** 2)
                ships_needed = target.ships + 1
                angle = math.atan2(target.y - mine.y, target.x - mine.x)
                move = [mine.id, angle, ships_needed]
                affordable = mine.ships >= ships_needed
                candidate = {
                    "candidate_id": _candidate_id(step, mine.id, target.id, ships_needed),
                    "candidate_type": "attack" if target.owner >= 0 else "expand",
                    "move": move,
                    "source_planet_id": mine.id,
                    "target_planet_id": target.id,
                    "ships": ships_needed,
                    "angle": angle,
                    "distance": distance,
                    "score": -distance,
                    "score_components": {
                        "distance_penalty": -distance,
                        "ships_needed": ships_needed,
                        "target_ships": target.ships,
                        "source_ships": mine.ships,
                        "source_reserve_after": mine.ships - ships_needed,
                        "target_owner": target.owner,
                        "target_production": target.production,
                    },
                    "legal": affordable,
                    "rejection_reason": None if affordable else "insufficient_source_ships",
                    "reason": f"nearest capturable non-owned planet from source {mine.id}",
                }
                source_candidates.append(candidate)

            legal_candidates = [candidate for candidate in source_candidates if candidate["legal"]]
            nearest = min(legal_candidates, key=lambda candidate: candidate["distance"], default=None)
            for candidate in source_candidates:
                if nearest is not None and candidate["candidate_id"] == nearest["candidate_id"]:
                    moves.append(candidate["move"])
                    decision["chosen_candidate_ids"].append(candidate["candidate_id"])
                elif candidate["legal"]:
                    candidate["rejection_reason"] = "not_nearest_target_for_source"
                decision["candidates"].append(candidate)

        decision["chosen_moves"] = moves
        if moves:
            decision["chosen_reason"] = "selected nearest legal capturable target per owned planet"
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
