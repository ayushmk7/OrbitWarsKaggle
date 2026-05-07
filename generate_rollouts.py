"""Generate local Orbit Wars rollout data for debugging and DPO prep."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import main as main_agent


SCHEMA_VERSION = 2
GENERATOR_VERSION = "rollout_generator_v2_decision_trace"


def as_plain(value: Any) -> Any:
    """Convert Kaggle Struct objects into JSON-serializable containers."""
    if isinstance(value, dict):
        return {key: as_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_plain(item) for item in value]
    return value


def summarize_final_step(final_step: list[dict[str, Any]]) -> dict[str, Any]:
    final_ship_scores = compute_final_ship_scores(final_step)
    return {
        "rewards": [agent.get("reward") for agent in final_step],
        "statuses": [agent.get("status") for agent in final_step],
        "final_steps": [
            agent.get("observation", {}).get("step")
            for agent in final_step
        ],
        "final_ship_scores": final_ship_scores,
        "winner_agent_index": winner_agent_index(final_ship_scores),
    }


def compute_final_ship_scores(final_step: list[dict[str, Any]]) -> list[int | None]:
    """Compute each player score from final planets and fleets."""
    board_observation = next(
        (
            agent.get("observation", {})
            for agent in final_step
            if agent.get("observation")
        ),
        {},
    )
    planets = board_observation.get("planets", [])
    fleets = board_observation.get("fleets", [])

    scores = []
    for agent_index, agent in enumerate(final_step):
        observation = agent.get("observation", {})
        player = observation.get("player", agent_index)
        if player is None:
            scores.append(None)
            continue
        planet_ships = sum(planet[5] for planet in planets if planet[1] == player)
        fleet_ships = sum(fleet[6] for fleet in fleets if fleet[1] == player)
        scores.append(planet_ships + fleet_ships)
    return scores


def winner_agent_index(scores: list[int | None]) -> int | None:
    numeric_scores = [(index, score) for index, score in enumerate(scores) if score is not None]
    if not numeric_scores:
        return None
    max_score = max(score for _, score in numeric_scores)
    winners = [index for index, score in numeric_scores if score == max_score]
    return winners[0] if len(winners) == 1 else None


def agent_versions_for(agents: list[str]) -> list[str]:
    versions = []
    for agent in agents:
        if agent == "main.py":
            versions.append(main_agent.AGENT_VERSION)
        elif agent == "random":
            versions.append("builtin_random")
        else:
            versions.append("unknown")
    return versions


def build_metadata(
    *,
    seed: int,
    agents: list[str],
    configuration: Any,
    final_summary: dict[str, Any],
    run_started_at: str,
    run_finished_at: str,
    duration_ms: float,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generated_at": run_finished_at,
        "run_started_at": run_started_at,
        "run_finished_at": run_finished_at,
        "duration_ms": duration_ms,
        "environment": "orbit_wars",
        "seed": seed,
        "agents": agents,
        "agent_versions": agent_versions_for(agents),
        "configuration": as_plain(configuration),
        "errors": errors,
        **final_summary,
    }


def _moves_equal(left: Any, right: Any) -> bool:
    return json.dumps(as_plain(left), sort_keys=True) == json.dumps(as_plain(right), sort_keys=True)


def build_agent_decisions(
    step: list[dict[str, Any]],
    agents: list[str],
    action_step: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    decisions = []
    errors = []

    for agent_index, agent_name in enumerate(agents):
        if agent_name != "main.py" or agent_index >= len(step):
            continue

        agent_step = step[agent_index]
        observation = agent_step.get("observation")
        if not observation:
            continue

        trace = main_agent.decide_with_trace(observation)
        decision = {
            "agent_index": agent_index,
            "agent_name": agent_name,
            **trace["decision"],
        }
        decisions.append(decision)

        recorded_action = None
        if action_step is not None and agent_index < len(action_step):
            recorded_action = action_step[agent_index].get("action")

        if recorded_action is not None and agent_step.get("status") == "ACTIVE" and not _moves_equal(
            decision["chosen_moves"],
            recorded_action,
        ):
            errors.append(
                {
                    "type": "action_mismatch",
                    "agent_index": agent_index,
                    "agent_name": agent_name,
                    "recorded_action": recorded_action,
                    "traced_action": decision["chosen_moves"],
                    "turn": observation.get("step"),
                }
            )

    return decisions, errors


def generate_rollout(seed: int, agents: list[str], output_dir: Path) -> dict[str, Any]:
    try:
        from kaggle_environments import make
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "kaggle_environments is required to generate rollouts. "
            'Install it with: pip install "kaggle-environments>=1.28.0"'
        ) from exc

    run_started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    env = make("orbit_wars", configuration={"seed": seed}, debug=True)
    steps = as_plain(env.run(agents))
    duration_ms = (time.perf_counter() - started) * 1000
    run_finished_at = datetime.now(timezone.utc).isoformat()
    final_summary = summarize_final_step(steps[-1])
    errors = []
    step_records = []

    for turn, step in enumerate(steps):
        action_step = steps[turn + 1] if turn + 1 < len(steps) else None
        agent_decisions, decision_errors = build_agent_decisions(step, agents, action_step)
        errors.extend(decision_errors)
        step_records.append(
            {
                "type": "step",
                "schema_version": SCHEMA_VERSION,
                "seed": seed,
                "turn": turn,
                "agents": step,
                "agent_decisions": agent_decisions,
            }
        )

    metadata = build_metadata(
        seed=seed,
        agents=agents,
        configuration=env.configuration,
        final_summary=final_summary,
        run_started_at=run_started_at,
        run_finished_at=run_finished_at,
        duration_ms=duration_ms,
        errors=errors,
    )

    output_path = output_dir / f"{main_agent.AGENT_VERSION}_vs_random_seed_{seed:04d}.jsonl"
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "metadata", **metadata}) + "\n")
        for record in step_records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")

    return {
        "seed": seed,
        "output_path": str(output_path),
        "num_steps": len(steps),
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "agent_versions": agent_versions_for(agents),
        "duration_ms": duration_ms,
        "errors": errors,
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
