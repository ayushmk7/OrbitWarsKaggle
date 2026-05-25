"""Evaluate the current Orbit Wars agent across fixed local seeds."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import generate_rollouts
import main


DEFAULT_OUTPUT_DIR = Path("data/rollouts_v2") / main.AGENT_VERSION
DEFAULT_SUMMARY_PATH = Path("results") / f"quick_{main.AGENT_VERSION}.json"


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _classify_first_agent(result: dict[str, Any]) -> str:
    rewards = result.get("rewards") or []
    reward = rewards[0] if rewards else None
    if reward == 1:
        return "win"
    if reward == -1:
        return "loss"
    if reward == 0:
        return "tie"

    winner_agent_index = result.get("winner_agent_index")
    if winner_agent_index == 0:
        return "win"
    if winner_agent_index is None:
        return "tie"
    return "loss"


def summarize_results(
    *,
    results: list[dict[str, Any]],
    agents: list[str],
    start_seed: int,
    games: int,
    opponents: list[str],
    generated_at: str,
) -> dict[str, Any]:
    outcomes = [_classify_first_agent(result) for result in results]
    wins = outcomes.count("win")
    losses = outcomes.count("loss")
    ties = outcomes.count("tie")
    rewards = [
        result.get("rewards", [0])[0]
        for result in results
        if result.get("rewards") and result.get("rewards")[0] is not None
    ]
    final_ship_scores = [
        result.get("final_ship_scores", [0])[0]
        for result in results
        if result.get("final_ship_scores") and result.get("final_ship_scores")[0] is not None
    ]
    durations = [result.get("duration_ms", 0.0) for result in results]
    error_count = sum(len(result.get("errors", [])) for result in results)

    return {
        "generated_at": generated_at,
        "agent_version": main.AGENT_VERSION,
        "agents": agents,
        "opponents": opponents,
        "start_seed": start_seed,
        "games": games,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "win_rate": wins / games if games else 0.0,
        "average_reward": _average(rewards),
        "average_final_ship_score": _average(final_ship_scores),
        "average_duration_ms": _average(durations),
        "error_count": error_count,
        "results": results,
    }


def _parse_opponents(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return value
    return [opponent.strip() for opponent in value.split(",") if opponent.strip()]


def run_evaluation(
    *,
    start_seed: int,
    games: int,
    opponents: list[str],
    summary_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    agents = ["main.py", *opponents]
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    results = [
        generate_rollouts.generate_rollout(seed, agents, output_dir)
        for seed in range(start_seed, start_seed + games)
    ]
    summary = summarize_results(
        results=results,
        agents=agents,
        start_seed=start_seed,
        games=games,
        opponents=opponents,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--opponents", default="random")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main_cli() -> None:
    args = parse_args()
    opponents = _parse_opponents(args.opponents)
    summary = run_evaluation(
        start_seed=args.start_seed,
        games=args.games,
        opponents=opponents,
        summary_path=args.summary,
        output_dir=args.output_dir,
    )
    print(f"Agent version: {summary['agent_version']}")
    print(f"Games: {summary['games']}")
    print(f"Wins: {summary['wins']}/{summary['games']}")
    print(f"Win rate: {summary['win_rate']:.3f}")
    print(f"Errors: {summary['error_count']}")
    print(f"Summary: {args.summary}")


if __name__ == "__main__":
    main_cli()
