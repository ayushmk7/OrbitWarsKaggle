import math

import pytest

import main
import prediction


def test_predict_orbit_position_zero_turns_returns_initial_position():
    planet = main.Planet(1, -1, 70.0, 50.0, 1.0, 5, 3)

    x, y = prediction.predict_orbit_position(planet, angular_velocity=0.1, turns=0)

    assert x == pytest.approx(70.0)
    assert y == pytest.approx(50.0)


def test_predict_orbit_position_keeps_orbital_radius_constant():
    planet = main.Planet(1, -1, 70.0, 50.0, 1.0, 5, 3)

    x, y = prediction.predict_orbit_position(planet, angular_velocity=0.2, turns=7)

    assert math.hypot(x - 50.0, y - 50.0) == pytest.approx(20.0)


def test_predict_orbit_position_positive_velocity_rotates_expected_direction():
    planet = main.Planet(1, -1, 70.0, 50.0, 1.0, 5, 3)

    x, y = prediction.predict_orbit_position(planet, angular_velocity=math.pi / 2, turns=1)

    assert x == pytest.approx(50.0)
    assert y == pytest.approx(70.0)


def test_sample_orbit_intercept_returns_deterministic_angle_for_simple_case():
    source = main.Planet(1, 0, 70.0, 50.0, 1.0, 20, 3)
    target = main.Planet(2, -1, 75.0, 50.0, 1.0, 1, 4)
    initial_target = main.Planet(2, -1, 75.0, 50.0, 1.0, 1, 4)

    intercept = prediction.sample_orbit_intercept(
        source,
        target,
        initial_target,
        angular_velocity=0.0,
        ships=2,
        max_turns=10,
        timing_tolerance=10.0,
    )

    assert intercept is not None
    assert intercept["angle"] == pytest.approx(0.0)
    assert intercept["predicted_target"] == pytest.approx((75.0, 50.0))


def test_orbit_candidate_uses_initial_planets_not_current_radius():
    obs = {
        "player": 0,
        "step": 5,
        "angular_velocity": 0.0,
        "initial_planets": [
            [1, 0, 70.0, 40.0, 1.0, 50, 3],
            [2, -1, 75.0, 50.0, 1.0, 1, 5],
        ],
        "planets": [
            [1, 0, 70.0, 40.0, 1.0, 50, 3],
            [2, -1, 75.0, 50.0, 1.0, 1, 5],
        ],
        "fleets": [],
    }

    result = main.decide_with_trace(obs)
    candidate = result["decision"]["candidates"][0]

    assert candidate["score_components"]["target_is_orbiting"] is True
    assert candidate["score_components"]["used_initial_planet"] is True
    assert candidate["score_components"]["predicted_target_x"] == pytest.approx(75.0)
    assert candidate["score_components"]["predicted_target_y"] == pytest.approx(50.0)


def test_orbit_candidate_rejected_when_intercept_hits_sun():
    obs = {
        "player": 0,
        "step": 5,
        "angular_velocity": 0.0,
        "initial_planets": [
            [1, 0, 20.0, 50.0, 1.0, 50, 3],
            [2, -1, 75.0, 50.0, 1.0, 1, 5],
        ],
        "planets": [
            [1, 0, 20.0, 50.0, 1.0, 50, 3],
            [2, -1, 75.0, 50.0, 1.0, 1, 5],
        ],
        "fleets": [],
    }

    result = main.decide_with_trace(obs)
    candidate = result["decision"]["candidates"][0]

    assert candidate["legal"] is False
    assert candidate["rejection_reason"] == "orbit_intercept_sun_blocked"


def test_static_candidate_behavior_still_matches_direct_geometry():
    obs = {
        "player": 0,
        "step": 5,
        "angular_velocity": 0.1,
        "initial_planets": [
            [1, 0, 0.0, 0.0, 1.0, 50, 3],
            [2, -1, 90.0, 90.0, 1.0, 1, 5],
        ],
        "planets": [
            [1, 0, 0.0, 0.0, 1.0, 50, 3],
            [2, -1, 90.0, 90.0, 1.0, 1, 5],
        ],
        "fleets": [],
    }

    result = main.decide_with_trace(obs)
    candidate = result["decision"]["candidates"][0]

    assert candidate["score_components"]["target_is_orbiting"] is False
    assert candidate["angle"] == pytest.approx(math.atan2(90.0, 90.0))
