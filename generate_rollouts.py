"""Generate local Orbit Wars rollout data for debugging and DPO prep."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kaggle_environments import make


def as_plain(value: Any) -> Any:
    """Convert Kaggle Struct objects into JSON-serializable containers."""
    if isinstance(value, dict):
        return {key: as_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_plain(item) for item in value]
    return value


def summarize_final_step(final_step: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rewards": [agent.get("reward") for agent in final_step],
        "statuses": [agent.get("status") for agent in final_step],
        "final_steps": [
            agent.get("observation", {}).get("step")
            for agent in final_step
        ],
    }


def generate_rollout(seed: int, agents: list[str], output_dir: Path) -> dict[str, Any]:
    env = make("orbit_wars", configuration={"seed": seed}, debug=True)
    steps = as_plain(env.run(agents))
    final_summary = summarize_final_step(steps[-1])

    metadata = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "orbit_wars",
        "seed": seed,
        "agents": agents,
        "configuration": as_plain(env.configuration),
        **final_summary,
    }

    output_path = output_dir / f"main_vs_random_seed_{seed:04d}.jsonl"
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "metadata", **metadata}) + "\n")
        for turn, step in enumerate(steps):
            handle.write(
                json.dumps(
                    {
                        "type": "step",
                        "seed": seed,
                        "turn": turn,
                        "agents": step,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )

    return {
        "seed": seed,
        "output_path": str(output_path),
        "num_steps": len(steps),
        **final_summary,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--output-dir", type=Path, default=Path("data/rollouts"))
    parser.add_argument("--summary", type=Path, default=Path("results/local_rollouts_summary.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.summary.parent.mkdir(parents=True, exist_ok=True)

    agents = ["main.py", "random"]
    results = [
        generate_rollout(seed, agents, args.output_dir)
        for seed in range(args.start_seed, args.start_seed + args.games)
    ]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agents": agents,
        "start_seed": args.start_seed,
        "games": args.games,
        "results": results,
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    wins = sum(1 for result in results if result["rewards"][0] == 1)
    print(f"Generated {len(results)} rollouts in {args.output_dir}")
    print(f"Agent 0 wins: {wins}/{len(results)}")
    print(f"Summary: {args.summary}")


if __name__ == "__main__":
    main()
