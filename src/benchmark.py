"""Benchmark the Orbit Wars agent against real opponents.

The agent already beats `random` ~99%, which is no signal. This harness pits the
current `main.agent` against meaningful opponents:

  * builtin `random`
  * builtin `starter` (static-planet sniper -- the competition starter agent)
  * a frozen previous version (self-play, new vs old) loaded from ./baseline
  * 4-player free-for-all (new agent in seat 0 vs starter/baseline/random)

Run from the repo root with the venv active:

    python -m benchmark --games 40 --start-seed 1 --opponents starter,baseline,random
    python -m benchmark --games 20 --mode 4p

Win rate vs `starter` and vs `baseline` (self-play) is the primary quality
signal for Solution A changes -- NOT win rate vs random.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Running ``python -m benchmark`` from the repo root puts the repo root (cwd)
# at sys.path[0], which shadows src/main.py with the stale root main.py. Force
# this file's own directory (src/) to the front so ``import main`` is the
# canonical agent.
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.path and sys.path[0] != _SRC_DIR:
    sys.path.insert(0, _SRC_DIR)

import main as main_agent

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_DIR = REPO_ROOT / "baseline"


def _load_baseline_agent() -> Callable[[Any], list]:
    """Load the frozen previous-version agent as an isolated callable.

    The baseline ships its own renamed geometry_v1/prediction_v1 modules so it
    never picks up the live (improved) geometry.py / prediction.py.
    """
    if str(BASELINE_DIR) not in sys.path:
        sys.path.insert(0, str(BASELINE_DIR))
    spec = importlib.util.spec_from_file_location(
        "agent_v1", str(BASELINE_DIR / "agent_v1.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_v1"] = module
    spec.loader.exec_module(module)
    return module.agent


def _builtin_agent(name: str) -> Callable[[Any], list]:
    from kaggle_environments.envs.orbit_wars.orbit_wars import agents as builtin

    return builtin[name]


def resolve_agent(name: str) -> Callable[[Any], list]:
    """Map an opponent name to a callable agent."""
    if name in ("main", "self", "new"):
        return main_agent.agent
    if name == "baseline":
        return _load_baseline_agent()
    if name in ("random", "starter"):
        return _builtin_agent(name)
    raise ValueError(f"unknown opponent: {name}")


def _final_scores(final_step: list[dict[str, Any]]) -> list[int]:
    obs = next(
        (a.get("observation", {}) for a in final_step if a.get("observation")), {}
    )
    planets = obs.get("planets", [])
    fleets = obs.get("fleets", [])
    num = len(final_step)
    scores = [0] * num
    for p in planets:
        if 0 <= p[1] < num:
            scores[p[1]] += p[5]
    for f in fleets:
        if 0 <= f[1] < num:
            scores[f[1]] += f[6]
    return scores


def play_game(seat_agents: list[Callable], seed: int) -> dict[str, Any]:
    from kaggle_environments import make

    env = make("orbit_wars", configuration={"seed": seed}, debug=False)
    env.run(seat_agents)
    final = env.steps[-1]
    scores = _final_scores(final)
    my_score = scores[0]
    best_other = max(scores[1:]) if len(scores) > 1 else 0
    if my_score > best_other:
        outcome = "win"
    elif my_score == best_other:
        outcome = "tie"
    else:
        outcome = "loss"
    return {
        "seed": seed,
        "scores": scores,
        "my_score": my_score,
        "best_other": best_other,
        "outcome": outcome,
        "final_step": final[0].get("observation", {}).get("step"),
    }


def run_matchup(
    opponent: str, games: int, start_seed: int, mode: str
) -> dict[str, Any]:
    new_agent = resolve_agent("main")
    if mode == "4p":
        # seat 0 = new agent, seats 1-3 = a mix to simulate FFA
        opp = resolve_agent(opponent)
        seat_agents = [new_agent, opp, resolve_agent("baseline"), resolve_agent("starter")]
    else:
        seat_agents = [new_agent, resolve_agent(opponent)]

    results = []
    started = time.perf_counter()
    for seed in range(start_seed, start_seed + games):
        results.append(play_game(seat_agents, seed))
    duration = time.perf_counter() - started

    wins = sum(1 for r in results if r["outcome"] == "win")
    losses = sum(1 for r in results if r["outcome"] == "loss")
    ties = sum(1 for r in results if r["outcome"] == "tie")
    avg_margin = sum(r["my_score"] - r["best_other"] for r in results) / max(1, len(results))
    return {
        "opponent": opponent,
        "mode": mode,
        "games": games,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_rate": wins / max(1, games),
        "avg_score_margin": avg_margin,
        "avg_my_score": sum(r["my_score"] for r in results) / max(1, len(results)),
        "duration_s": duration,
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=30)
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument("--opponents", default="starter,baseline,random")
    parser.add_argument("--mode", choices=["2p", "4p"], default="2p")
    parser.add_argument("--summary", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    opponents = [o.strip() for o in args.opponents.split(",") if o.strip()]
    matchups = []
    for opp in opponents:
        m = run_matchup(opp, args.games, args.start_seed, args.mode)
        matchups.append(m)
        print(
            f"vs {opp:<10} [{args.mode}]  "
            f"W{m['wins']:>3} L{m['losses']:>3} T{m['ties']:>3}  "
            f"win_rate={m['win_rate']:.3f}  "
            f"avg_margin={m['avg_score_margin']:+.1f}  "
            f"({m['duration_s']:.1f}s)"
        )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent_version": main_agent.AGENT_VERSION,
        "games": args.games,
        "start_seed": args.start_seed,
        "mode": args.mode,
        "matchups": matchups,
    }
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"Summary: {args.summary}")


if __name__ == "__main__":
    main()
