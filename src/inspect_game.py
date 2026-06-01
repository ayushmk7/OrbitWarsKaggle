"""Inspect a single seeded Orbit Wars game turn-by-turn.

Productizes the ad-hoc trajectory/decision scripts used while debugging the
orbit-intercept loss cluster. Run one game on a fixed seed against any opponent
and see the per-player economy trajectory, the final result, and (optionally)
our agent's chosen moves + candidate-rejection breakdown at a given step.

    PYTHONPATH=src python -m inspect_game --seed 5 --opponent starter
    PYTHONPATH=src python -m inspect_game --seed 18 --opponent starter --every 10
    PYTHONPATH=src python -m inspect_game --seed 18 --decisions-at 30

Win-rate signal comes from `benchmark`; this tool answers "WHAT went wrong in
THIS game" -- the lead-then-collapse / hoarding / missed-expansion patterns.
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter

# Silence kaggle_environments' import-time OpenSpiel INFO spam (see benchmark.py).
logging.disable(logging.INFO)

import benchmark as B  # resolve_agent, _final_scores, _SRC_DIR path fix
import main


def _player_stats(obs, player):
    """(#planets, total production, total ships incl. fleets) for a player."""
    planets = ships = production = 0
    for p in obs.get("planets", []):
        if p[1] == player:
            planets += 1
            ships += p[5]
            production += p[6]
    for f in obs.get("fleets", []):
        if f[1] == player:
            ships += f[6]
    return planets, production, ships


def _num_players(obs):
    owners = {p[1] for p in obs.get("planets", []) if p[1] >= 0}
    owners |= {f[1] for f in obs.get("fleets", []) if f[1] >= 0}
    return max(2, max(owners) + 1 if owners else 2)


def inspect(seed: int, opponent: str, every: int, decisions_at: int | None) -> None:
    from kaggle_environments import make

    seat_agents = [B.resolve_agent("main"), B.resolve_agent(opponent)]
    env = make("orbit_wars", configuration={"seed": seed}, debug=False)
    env.run(seat_agents)

    steps = env.steps
    obs0 = steps[0][0]["observation"]
    nplayers = _num_players(obs0)
    av = obs0.get("angular_velocity")
    print(f"seed={seed}  opponent={opponent}  players={nplayers}  "
          f"angular_velocity={av:.4f}  total_steps={len(steps)}")
    print(f"{'step':>5} | " + " | ".join(
        f"P{p}(plan,prod,ships)" for p in range(nplayers)))

    last = len(steps) - 1
    for i, st in enumerate(steps):
        if i % every != 0 and i != last:
            continue
        obs = st[0]["observation"]
        cols = []
        for p in range(nplayers):
            n, prod, sh = _player_stats(obs, p)
            cols.append(f"{n:>2},{prod:>3},{sh:>5}")
        print(f"{obs.get('step', i):>5} | " + " | ".join(cols))

    scores = B._final_scores(steps[-1])
    me = scores[0]
    best_other = max(scores[1:]) if len(scores) > 1 else 0
    outcome = "WIN" if me > best_other else ("TIE" if me == best_other else "LOSS")
    print(f"\nRESULT: {outcome}  scores={scores}  (me={me} vs best_other={best_other})")

    if decisions_at is not None:
        _show_decisions(steps, decisions_at)


def _show_decisions(steps, step_idx: int) -> None:
    if step_idx >= len(steps):
        print(f"\n[decisions] step {step_idx} out of range (game ended at {len(steps)-1})")
        return
    obs = dict(steps[step_idx][0]["observation"])
    obs["player"] = 0
    decision = main.decide_with_trace(obs)["decision"]
    print(f"\n[decisions @ step {step_idx}]  chosen_moves={decision['chosen_moves']}")
    print(f"  chosen_reason: {decision.get('chosen_reason')}")
    cands = decision.get("candidates", [])
    reasons = Counter(c.get("rejection_reason") for c in cands if not c.get("legal"))
    print(f"  candidates: {len(cands)}  rejections: {dict(reasons)}")
    legal = [c for c in cands if c.get("legal")]
    legal.sort(key=lambda c: -c.get("score", 0))
    for c in legal[:5]:
        print(f"    LEGAL {c['candidate_type']:>10} src{c['source_planet_id']}->"
              f"tgt{c['target_planet_id']} ships={c['ships']} score={c['score']:.0f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--opponent", default="starter")
    parser.add_argument("--every", type=int, default=15, help="print every Nth turn")
    parser.add_argument(
        "--decisions-at",
        type=int,
        default=None,
        help="also dump our agent's moves + candidate rejections at this step",
    )
    return parser.parse_args()


def main_cli() -> None:
    args = parse_args()
    inspect(args.seed, args.opponent, args.every, args.decisions_at)


if __name__ == "__main__":
    main_cli()
