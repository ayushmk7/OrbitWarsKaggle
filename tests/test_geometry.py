import math

import pytest

import geometry


def test_distance_xy_uses_euclidean_distance():
    assert geometry.distance_xy(0.0, 0.0, 3.0, 4.0) == 5.0


def test_angle_to_xy_covers_cardinal_and_diagonal_directions():
    assert geometry.angle_to_xy(0.0, 0.0, 1.0, 0.0) == 0.0
    assert geometry.angle_to_xy(0.0, 0.0, 0.0, 1.0) == pytest.approx(math.pi / 2)
    assert geometry.angle_to_xy(0.0, 0.0, -1.0, 0.0) == pytest.approx(math.pi)
    assert geometry.angle_to_xy(0.0, 0.0, 1.0, 1.0) == pytest.approx(math.pi / 4)


def test_fleet_speed_increases_with_ship_count_and_respects_cap():
    speeds = [geometry.fleet_speed(ships) for ships in [1, 2, 10, 100, 1000]]

    assert speeds == sorted(speeds)
    assert speeds[0] == 1.0
    assert speeds[-1] <= 6.0


def test_turns_to_reach_ceilings_distance_over_speed():
    assert geometry.turns_to_reach(10.0, 1) == 10
    assert geometry.turns_to_reach(0.0, 10) == 0
    assert geometry.turns_to_reach(1.1, 1) == 2


def test_segment_intersects_circle_detects_through_miss_and_tangent():
    assert geometry.segment_intersects_circle(0.0, 0.0, 10.0, 0.0, 5.0, 0.0, 1.0)
    assert not geometry.segment_intersects_circle(0.0, 2.0, 10.0, 2.0, 5.0, 0.0, 1.0)
    assert geometry.segment_intersects_circle(0.0, 1.0, 10.0, 1.0, 5.0, 0.0, 1.0)


def test_segment_intersects_circle_handles_zero_length_segment():
    assert geometry.segment_intersects_circle(5.0, 0.0, 5.0, 0.0, 5.0, 0.0, 1.0)
    assert not geometry.segment_intersects_circle(7.0, 0.0, 7.0, 0.0, 5.0, 0.0, 1.0)


def test_shot_hits_sun_uses_orbit_wars_sun_defaults():
    assert geometry.shot_hits_sun((20.0, 50.0), (80.0, 50.0))
    assert not geometry.shot_hits_sun((20.0, 20.0), (80.0, 20.0))
