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


AGENT_VERSION = "rule_based_submission_v1"
MAX_TURNS = 500
EARLY_GAME_END = 150
LATE_GAME_START = 400
ENDGAME_START = 470
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


def _reinforce_candidate_id(step, source_id, target_id, fleet_id, ships):
    return f"{AGENT_VERSION}:t{step}:p{source_id}->p{target_id}:f{fleet_id}:{ships}"


def _game_phase(step):
    if step < EARLY_GAME_END:
        return "early"
    if step >= LATE_GAME_START:
        return "late"
    return "mid"


def _is_endgame(step):
    return step >= ENDGAME_START


def _arrives_before_end(step, travel_turns):
    return step + travel_turns <= MAX_TURNS


def _endgame_candidate_bonus(step, target, travel_turns, is_attack):
    if not _is_endgame(step):
        return 0
    if not _arrives_before_end(step, travel_turns):
        return -1000
    capture_value = target.ships + max(0, target.production) * max(0, MAX_TURNS - step)
    denial_multiplier = 2 if is_attack else 1
    return capture_value * denial_multiplier


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


def _score_candidate(mine, target, step, ships_needed, distance, travel_turns, sun_blocked, orbit_trace):
    remaining_after_arrival = max(0, MAX_TURNS - step - travel_turns)
    source_reserve_after = mine.ships - ships_needed
    base_reserve = max(1, mine.production)
    base_reserve_penalty = max(0, base_reserve - source_reserve_after)
    production_value = target.production * remaining_after_arrival
    endgame_bonus = _endgame_candidate_bonus(step, target, travel_turns, is_attack=False)
    ship_cost = ships_needed
    travel_cost = travel_turns
    preliminary_score = production_value + endgame_bonus - ship_cost - travel_cost - base_reserve_penalty
    desired_reserve = _desired_reserve(mine, step, preliminary_score)
    reserve_penalty = max(0, desired_reserve - source_reserve_after)
    score = production_value + endgame_bonus - ship_cost - travel_cost - reserve_penalty
    score_components = {
        "production_value": production_value,
        "endgame_bonus": endgame_bonus,
        "arrives_before_end": _arrives_before_end(step, travel_turns),
        "turns_remaining": max(0, MAX_TURNS - step),
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


def _score_attack_candidate(mine, target, step, ships_needed, distance, travel_turns, sun_blocked, orbit_trace):
    remaining_after_arrival = max(0, MAX_TURNS - step - travel_turns)
    source_reserve_after = mine.ships - ships_needed
    expected_production = max(0, target.production) * travel_turns
    margin = _attack_margin(target)
    base_reserve = max(1, mine.production)
    production_value = target.production * remaining_after_arrival
    enemy_denial_value = target.production * max(0, remaining_after_arrival // 2)
    weak_garrison_bonus = max(0, 20 - target.ships) * 10
    endgame_bonus = _endgame_candidate_bonus(step, target, travel_turns, is_attack=True)
    ship_cost = ships_needed
    travel_cost = travel_turns * 2
    preliminary_score = production_value + enemy_denial_value + weak_garrison_bonus + endgame_bonus - ship_cost - travel_cost
    desired_reserve = _desired_reserve(mine, step, preliminary_score)
    reserve_penalty = max(0, desired_reserve - source_reserve_after) * 2
    score = production_value + enemy_denial_value + weak_garrison_bonus + endgame_bonus - ship_cost - travel_cost - reserve_penalty
    score_components = {
        "production_value": production_value,
        "enemy_denial_value": enemy_denial_value,
        "weak_garrison_bonus": weak_garrison_bonus,
        "endgame_bonus": endgame_bonus,
        "arrives_before_end": _arrives_before_end(step, travel_turns),
        "turns_remaining": max(0, MAX_TURNS - step),
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


def _attack_overextends_source(mine, ships_needed, desired_reserve):
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

        # Parse into named tuples for readable field access:
        #   Planet(id, owner, x, y, radius, ships, production)
        #   owner == -1 means neutral, 0-3 are player IDs
        planets = [Planet(*p) for p in raw_planets]
        fleets = [Fleet(*f) for f in raw_fleets]
        initial_planets = [Planet(*p) for p in (raw_initial_planets or [])]
        initial_by_id = prediction.planet_by_id(initial_planets)
        my_planets = [p for p in planets if p.owner == player]
        enemy_fleets = [f for f in fleets if f.owner != player and f.owner >= 0]
        targets = [p for p in planets if p.owner != player]
        source_budgets = {planet.id: planet.ships for planet in my_planets}

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
            return {"moves": moves, "decision": decision}

        for mine in my_planets:
            source_candidates = []
            for target in targets:
                is_attack = target.owner >= 0
                ships_needed = target.ships + 1
                static_distance = geometry.distance_xy(mine.x, mine.y, target.x, target.y)
                static_travel_turns = geometry.turns_to_reach(static_distance, ships_needed)
                if is_attack:
                    ships_needed, static_travel_turns = _attack_ships_and_travel(
                        target,
                        static_distance,
                        static_travel_turns,
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
                
                move = [mine.id, angle, ships_needed]
                if is_attack:
                    score, score_components, desired_reserve = _score_attack_candidate(
                        mine,
                        target,
                        step,
                        ships_needed,
                        distance,
                        travel_turns,
                        sun_blocked,
                        orbit_trace,
                    )
                else:
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
                attack_overextended = (
                    is_attack
                    and affordable
                    and reserve_ok
                    and _attack_overextends_source(mine, ships_needed, desired_reserve)
                )
                too_late_to_arrive = _is_endgame(step) and not _arrives_before_end(step, travel_turns)
                legal = (
                    affordable
                    and reserve_ok
                    and not attack_overextended
                    and not too_late_to_arrive
                    and not sun_blocked
                    and orbit_rejection_reason is None
                )
                if too_late_to_arrive:
                    rejection_reason = "too_late_to_arrive"
                elif orbit_rejection_reason is not None:
                    rejection_reason = orbit_rejection_reason
                elif sun_blocked:
                    rejection_reason = "sun_blocked"
                elif not affordable:
                    rejection_reason = "insufficient_source_ships"
                elif not reserve_ok:
                    rejection_reason = "reserve_too_low"
                elif attack_overextended:
                    rejection_reason = "attack_overextension"
                else:
                    rejection_reason = None
                candidate = {
                    "candidate_id": _candidate_id(step, mine.id, target.id, ships_needed),
                    "candidate_type": "attack" if is_attack else "expand",
                    "move": move,
                    "source_planet_id": mine.id,
                    "target_planet_id": target.id,
                    "ships": ships_needed,
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
                    "reason": "opportunistic attack score" if is_attack else "highest production-adjusted expansion score",
                }
                source_candidates.append(candidate)

            selected = _select_budgeted_candidates(source_candidates, source_budgets[mine.id])
            selected_ids = {candidate["candidate_id"] for candidate in selected}
            for candidate in source_candidates:
                if candidate["candidate_id"] in selected_ids:
                    moves.append(candidate["move"])
                    decision["chosen_candidate_ids"].append(candidate["candidate_id"])
                    source_budgets[mine.id] -= candidate["ships"]
                decision["candidates"].append(candidate)
            
        decision["chosen_moves"] = moves
        if selected_defenses and len(moves) > len(selected_defenses):
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
