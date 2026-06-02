"""Fidelity: the simulator must reproduce the real env tick-by-tick.

Drives `kaggle_environments` orbit_wars, replays the recorded actions through
`simulator.step`, and asserts every planet's owner/ships and every fleet's
owner/ships match exactly, with positions within 1e-6, each tick.

Comet SPAWNS are seeded and hidden from agents, so the simulator cannot predict
them. The test injects newly-spawned comets from the real env (conceding only
the unpredictable spawn) and validates the simulator's comet advance/expiry.
"""

import logging

logging.disable(logging.INFO)  # silence kaggle_environments import spam

import pytest

import benchmark as B
import simulator

POS_TOL = 1e-6


def _inject_spawns(gs, obs):
    """Add comet groups present in the env obs but absent from the sim (a
    hidden spawn just happened). Existing comets keep advancing in-sim."""
    env_pids = set(obs.get("comet_planet_ids", []) or [])
    new = env_pids - set(gs.comet_pids)
    if not new:
        return
    env_p = {p[0]: p for p in obs["planets"]}
    have = {p[0] for p in gs.planets}
    for g in obs.get("comets", []) or []:
        if set(g["planet_ids"]) & new:
            gs.comets.append({
                "planet_ids": list(g["planet_ids"]),
                "paths": g["paths"],
                "path_index": g["path_index"],
            })
            for pid in g["planet_ids"]:
                gs.comet_pids.add(pid)
                if pid in env_p and pid not in have:
                    gs.planets.append(list(env_p[pid]))


def _assert_match(gs, obs, t):
    env_p = {p[0]: p for p in obs["planets"]}
    sim_p = {p[0]: p for p in gs.planets}
    assert set(env_p) == set(sim_p), f"t{t} planet-id mismatch"
    for pid, ep in env_p.items():
        sp = sim_p[pid]
        assert ep[1] == sp[1] and ep[5] == sp[5], (
            f"t{t} planet {pid} owner/ships env=({ep[1]},{ep[5]}) sim=({sp[1]},{sp[5]})")
        assert abs(ep[2] - sp[2]) < POS_TOL and abs(ep[3] - sp[3]) < POS_TOL, (
            f"t{t} planet {pid} position drift")
    env_f = {f[0]: f for f in obs["fleets"]}
    sim_f = {f[0]: f for f in gs.fleets}
    assert set(env_f) == set(sim_f), (
        f"t{t} fleet-id mismatch env-only={set(env_f)-set(sim_f)} sim-only={set(sim_f)-set(env_f)}")
    for fid, ef in env_f.items():
        sf = sim_f[fid]
        assert ef[1] == sf[1] and ef[6] == sf[6], f"t{t} fleet {fid} owner/ships"
        assert abs(ef[2] - sf[2]) < POS_TOL and abs(ef[3] - sf[3]) < POS_TOL, (
            f"t{t} fleet {fid} position drift")


def _run_fidelity(seed, max_ticks=None):
    from kaggle_environments import make

    me = B.resolve_agent("main")
    opp = B.resolve_agent("starter")
    env = make("orbit_wars", configuration={"seed": seed}, debug=False)
    env.run([me, opp])
    steps = env.steps
    gs = simulator.GameState.from_obs(steps[0][0]["observation"])
    T = len(steps) - 1
    if max_ticks is not None:
        T = min(T, max_ticks)
    for t in range(T):
        # The action that drives transition t -> t+1 is stored in steps[t+1]
        # (kaggle action-alignment), NOT steps[t].
        actions = {i: steps[t + 1][i]["action"] for i in range(len(steps[t + 1]))}
        simulator.step(gs, actions)
        obs = steps[t + 1][0]["observation"]
        _inject_spawns(gs, obs)
        _assert_match(gs, obs, t + 1)


# Short games (one player eliminated early) + one full 499-turn game with comets.
@pytest.mark.parametrize("seed", [1, 3, 18])
def test_fidelity_prefix(seed):
    _run_fidelity(seed, max_ticks=49)  # comet-free, fast


@pytest.mark.parametrize("seed", [5])
def test_fidelity_full_game_with_comets(seed):
    _run_fidelity(seed)  # 499 ticks incl. comet spawn/advance/expiry
