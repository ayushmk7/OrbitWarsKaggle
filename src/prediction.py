from __future__ import annotations

import math
from typing import Any

import geometry


def planet_by_id(planets: list[Any]) -> dict[int, Any]:
    return {planet.id: planet for planet in planets}


def is_orbiting_planet(
    planet: Any,
    center: tuple[float, float] = (50.0, 50.0),
    rotation_radius_limit: float = 50.0,
) -> bool:
    distance = geometry.distance_xy(center[0], center[1], planet.x, planet.y)
    return distance + planet.radius < rotation_radius_limit


def predict_orbit_position(
    initial_planet: Any,
    angular_velocity: float,
    turns: int,
    center: tuple[float, float] = (50.0, 50.0),
) -> tuple[float, float]:
    orbital_radius = geometry.distance_xy(center[0], center[1], initial_planet.x, initial_planet.y)
    initial_angle = math.atan2(initial_planet.y - center[1], initial_planet.x - center[0])
    future_angle = initial_angle + angular_velocity * turns
    return (
        center[0] + orbital_radius * math.cos(future_angle),
        center[1] + orbital_radius * math.sin(future_angle),
    )


def sample_orbit_intercept(
    source: Any,
    target: Any,
    initial_target: Any,
    angular_velocity: float,
    ships: int,
    max_turns: int = 80,
    timing_tolerance: float = 2.0,
) -> dict[str, Any] | None:
    best_sample = None
    best_error = float("inf")

    for intercept_turn in range(1, max_turns + 1):
        predicted_x, predicted_y = predict_orbit_position(
            initial_target,
            angular_velocity,
            intercept_turn,
        )
        distance = geometry.distance_xy(source.x, source.y, predicted_x, predicted_y)
        travel_turns = geometry.turns_to_reach(distance, ships)
        timing_error = abs(travel_turns - intercept_turn)
        sun_blocked = geometry.shot_hits_sun(
            (source.x, source.y),
            (predicted_x, predicted_y),
        )

        if timing_error < best_error:
            best_error = timing_error
            best_sample = {
                "angle": geometry.angle_to_xy(source.x, source.y, predicted_x, predicted_y),
                "distance": distance,
                "travel_turns": travel_turns,
                "intercept_turn": intercept_turn,
                "timing_error": timing_error,
                "predicted_target": (predicted_x, predicted_y),
                "sun_blocked": sun_blocked,
            }

    if best_sample is None or best_sample["timing_error"] > timing_tolerance:
        return None
    return best_sample
