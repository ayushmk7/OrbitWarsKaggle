"""Per-phase unit tests for the simulator (combat edges, collision parity)."""

import logging
import random

logging.disable(logging.INFO)

import simulator
from simulator import GameState


def _state(planets, fleets=None, step=1, num_players=2, av=0.0):
    initial = {p[0]: (p[2], p[3]) for p in planets}
    return GameState(
        [list(p) for p in planets],
        [list(f) for f in (fleets or [])],
        [], set(), initial, av, step,
        next_fleet_id=100, num_players=num_players,
    )


def test_swept_pair_hit_matches_env():
    """Our collision must equal the env's bit-for-bit on random inputs."""
    from kaggle_environments.envs.orbit_wars.orbit_wars import swept_pair_hit as env_hit

    rng = random.Random(12345)
    for _ in range(10000):
        A = (rng.uniform(0, 100), rng.uniform(0, 100))
        B = (rng.uniform(0, 100), rng.uniform(0, 100))
        P0 = (rng.uniform(0, 100), rng.uniform(0, 100))
        P1 = (rng.uniform(0, 100), rng.uniform(0, 100))
        r = rng.uniform(0.5, 5.0)
        assert simulator.swept_pair_hit(A, B, P0, P1, r) == env_hit(A, B, P0, P1, r)


def test_production_only_owned():
    s = _state([[1, 0, 10, 10, 1.0, 5, 3], [2, -1, 90, 90, 1.0, 5, 4]])
    simulator.step(s, {})
    by = {p[0]: p for p in s.planets}
    assert by[1][simulator.P_SHIPS] == 8   # owned: +3
    assert by[2][simulator.P_SHIPS] == 5   # neutral: unchanged


def test_launch_deducts_and_spawns_fleet():
    s = _state([[1, 0, 10, 10, 1.0, 20, 1]])
    simulator.step(s, {0: [[1, 0.0, 8]]})
    p1 = s.planets[0]
    assert p1[simulator.P_SHIPS] == 20 - 8 + 1   # launched 8, then +prod
    assert len(s.fleets) == 1 and s.fleets[0][simulator.F_SHIPS] == 8


def test_launch_rejects_overbudget_and_nonpositive():
    s = _state([[1, 0, 10, 10, 1.0, 5, 1]])
    simulator.step(s, {0: [[1, 0.0, 99], [1, 0.0, 0], [1, 0.0, -3]]})
    assert s.fleets == []                          # all illegal
    assert s.planets[0][simulator.P_SHIPS] == 6    # only production applied


def _combat_state(garrison_owner, garrison_ships, arrivals):
    """Planet at origin; fleets aimed straight at it from just outside."""
    planets = [[1, garrison_owner, 50.0, 50.0, 2.0, garrison_ships, 1]]
    fleets = []
    for i, (owner, ships) in enumerate(arrivals):
        # place a fleet adjacent and moving onto the planet centre
        fleets.append([200 + i, owner, 47.0, 50.0, 0.0, -1, ships])
    s = _state(planets, fleets, num_players=3)
    # neutralise garrison production for a clean assertion
    s.planets[0][simulator.P_PROD] = 0
    return s


def test_combat_single_attacker_flips_when_exceeding():
    s = _combat_state(garrison_owner=-1, garrison_ships=5, arrivals=[(0, 9)])
    simulator.step(s, {})
    p = s.planets[0]
    assert p[simulator.P_OWNER] == 0 and p[simulator.P_SHIPS] == 4  # 9-5


def test_combat_single_attacker_fails_when_short():
    s = _combat_state(garrison_owner=1, garrison_ships=10, arrivals=[(0, 6)])
    simulator.step(s, {})
    p = s.planets[0]
    assert p[simulator.P_OWNER] == 1 and p[simulator.P_SHIPS] == 4  # 10-6, no flip


def test_combat_two_attackers_top_minus_second():
    # owners 0 (12) and 2 (5) both hit a neutral-5 planet; survivor = 12-5 = 7,
    # then 7 vs garrison 5 -> flips to owner 0 with 2.
    s = _combat_state(garrison_owner=-1, garrison_ships=5, arrivals=[(0, 12), (2, 5)])
    simulator.step(s, {})
    p = s.planets[0]
    assert p[simulator.P_OWNER] == 0 and p[simulator.P_SHIPS] == 2


def test_combat_tie_annihilates():
    # equal top two -> survivor 0 -> garrison untouched.
    s = _combat_state(garrison_owner=-1, garrison_ships=5, arrivals=[(0, 8), (2, 8)])
    simulator.step(s, {})
    p = s.planets[0]
    assert p[simulator.P_OWNER] == -1 and p[simulator.P_SHIPS] == 5


def test_combat_reinforce_same_owner_adds():
    s = _combat_state(garrison_owner=0, garrison_ships=5, arrivals=[(0, 6)])
    simulator.step(s, {})
    p = s.planets[0]
    assert p[simulator.P_OWNER] == 0 and p[simulator.P_SHIPS] == 11  # 5 + 6


def test_clone_independence():
    s = _state([[1, 0, 10, 10, 1.0, 5, 3]], [[9, 0, 5, 5, 0.0, 1, 4]])
    c = s.clone()
    c.planets[0][simulator.P_SHIPS] = 999
    c.fleets[0][simulator.F_SHIPS] = 888
    c.step = 50
    assert s.planets[0][simulator.P_SHIPS] == 5
    assert s.fleets[0][simulator.F_SHIPS] == 4
    assert s.step == 1
    assert c.initial_by_id is s.initial_by_id  # read-only data shared
