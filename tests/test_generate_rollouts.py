import json

import generate_rollouts
import main


def test_compute_final_ship_scores_counts_planets_and_fleets():
    final_step = [
        {
            "observation": {
                "player": 0,
                "planets": [
                    [1, 0, 0.0, 0.0, 1.0, 10, 3],
                    [2, 1, 1.0, 1.0, 1.0, 7, 2],
                    [3, -1, 2.0, 2.0, 1.0, 99, 1],
                ],
                "fleets": [
                    [1, 0, 0.0, 0.0, 0.0, 1, 4],
                    [2, 1, 0.0, 0.0, 0.0, 2, 5],
                ],
            }
        },
        {
            "observation": {
                "player": 1,
                "planets": [
                    [1, 0, 0.0, 0.0, 1.0, 10, 3],
                    [2, 1, 1.0, 1.0, 1.0, 7, 2],
                ],
                "fleets": [
                    [1, 0, 0.0, 0.0, 0.0, 1, 4],
                    [2, 1, 0.0, 0.0, 0.0, 2, 5],
                ],
            }
        },
    ]

    assert generate_rollouts.compute_final_ship_scores(final_step) == [14, 12]


def test_winner_agent_index_uses_highest_final_ship_score():
    assert generate_rollouts.winner_agent_index([14, 12]) == 0
    assert generate_rollouts.winner_agent_index([12, 14]) == 1
    assert generate_rollouts.winner_agent_index([14, 14]) is None


def test_build_agent_decisions_records_main_trace_and_action_mismatch():
    step = [
        {
            "action": [],
            "status": "ACTIVE",
            "observation": {
                "player": 0,
                "step": 1,
                "planets": [
                    [1, 0, 0.0, 0.0, 1.0, 10, 3],
                    [2, -1, 3.0, 4.0, 1.0, 5, 2],
                ],
                "fleets": [],
            },
        },
        {"action": [], "status": "ACTIVE", "observation": {"player": 1}},
    ]

    action_step = [
        {"action": [], "status": "ACTIVE", "observation": {"player": 0}},
        {"action": [], "status": "ACTIVE", "observation": {"player": 1}},
    ]

    decisions, errors = generate_rollouts.build_agent_decisions(
        step,
        ["main.py", "random"],
        action_step,
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision["agent_index"] == 0
    assert decision["agent_name"] == "main.py"
    assert decision["agent_version"] == main.AGENT_VERSION
    assert decision["chosen_moves"] == [[1, 0.9272952180016122, 6]]
    assert decision["candidates"][0]["score"] == -5.0
    assert errors[0]["type"] == "action_mismatch"


def test_build_agent_decisions_compares_trace_to_next_step_action():
    step = [
        {
            "action": [],
            "status": "ACTIVE",
            "observation": {
                "player": 0,
                "step": 1,
                "planets": [
                    [1, 0, 0.0, 0.0, 1.0, 10, 3],
                    [2, -1, 3.0, 4.0, 1.0, 5, 2],
                ],
                "fleets": [],
            },
        },
        {"action": [], "status": "ACTIVE", "observation": {"player": 1}},
    ]
    action_step = [
        {"action": [[1, 0.9272952180016122, 6]], "status": "ACTIVE", "observation": {}},
        {"action": [], "status": "ACTIVE", "observation": {}},
    ]

    _, errors = generate_rollouts.build_agent_decisions(step, ["main.py", "random"], action_step)

    assert errors == []


def test_build_metadata_uses_schema_v2_and_is_json_serializable():
    final_summary = {
        "rewards": [1, -1],
        "statuses": ["DONE", "DONE"],
        "final_steps": [10, None],
        "final_ship_scores": [14, 12],
        "winner_agent_index": 0,
    }

    metadata = generate_rollouts.build_metadata(
        seed=7,
        agents=["main.py", "random"],
        configuration={"episodeSteps": 500},
        final_summary=final_summary,
        run_started_at="2026-01-01T00:00:00+00:00",
        run_finished_at="2026-01-01T00:00:01+00:00",
        duration_ms=1000.0,
        errors=[],
    )

    assert metadata["schema_version"] == 2
    assert metadata["generator_version"] == generate_rollouts.GENERATOR_VERSION
    assert metadata["agent_versions"] == [main.AGENT_VERSION, "builtin_random"]
    assert metadata["final_ship_scores"] == [14, 12]
    json.dumps({"type": "metadata", **metadata})
