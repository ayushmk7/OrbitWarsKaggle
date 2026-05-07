import json

import generate_rollouts
import main


def make_trace_obs(source_ships=10):
    return {
        "player": 0,
        "step": 1,
        "planets": [
            [1, 0, 0.0, 0.0, 1.0, source_ships, 3],
            [2, -1, 3.0, 4.0, 1.0, 5, 2],
        ],
        "fleets": [],
    }


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


def test_make_recording_agent_records_exact_decision_used_for_action():
    recorded_decisions = []
    recording_agent = generate_rollouts.make_recording_agent(
        0,
        "main.py",
        recorded_decisions,
    )

    moves = recording_agent(make_trace_obs())

    assert moves == [[1, 0.9272952180016122, 6]]
    assert len(recorded_decisions) == 1
    recorded = recorded_decisions[0]
    assert recorded["agent_index"] == 0
    assert recorded["agent_name"] == "main.py"
    assert recorded["observation_step"] == 1
    assert recorded["chosen_moves"] == moves
    assert recorded["chosen_reason"] == "selected highest-scoring legal production target per owned planet"


def test_build_agent_decisions_uses_recorded_decisions_without_recomputing(monkeypatch):
    step = [
        {
            "action": [],
            "status": "ACTIVE",
            "observation": make_trace_obs(),
        },
        {"action": [], "status": "ACTIVE", "observation": {"player": 1}},
    ]
    recorded_decisions = [
        {
            "agent_index": 0,
            "agent_name": "main.py",
            "observation_step": 1,
            "agent_version": main.AGENT_VERSION,
            "runtime_ms": 0.25,
            "error": None,
            "candidates": [],
            "chosen_candidate_ids": ["recorded"],
            "chosen_moves": [[1, 0.9272952180016122, 6]],
            "chosen_reason": "recorded during env.run",
            "recorded_during_run": True,
        }
    ]

    def fail_if_recomputed(_obs):
        raise AssertionError("decision should come from recorded run-time trace")

    monkeypatch.setattr(generate_rollouts.main_agent, "decide_with_trace", fail_if_recomputed)

    decisions, errors = generate_rollouts.build_agent_decisions(
        step,
        ["main.py", "random"],
        recorded_decisions=recorded_decisions,
    )

    assert errors == []
    assert decisions == recorded_decisions


def test_build_agent_decisions_falls_back_to_recomputed_decision_when_record_missing():
    step = [
        {
            "action": [],
            "status": "ACTIVE",
            "observation": make_trace_obs(),
        },
        {"action": [], "status": "ACTIVE", "observation": {"player": 1}},
    ]

    decisions, errors = generate_rollouts.build_agent_decisions(step, ["main.py", "random"])

    assert errors == []
    assert len(decisions) == 1
    assert decisions[0]["recorded_during_run"] is False
    assert decisions[0]["observation_step"] == 1
    assert decisions[0]["chosen_moves"] == [[1, 0.9272952180016122, 6]]


def test_build_agent_decisions_records_main_trace_without_action_mismatch_by_default():
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
    assert decision["candidates"][0]["score"] == 980
    assert decision["candidates"][0]["travel_turns"] == 4
    assert decision["candidates"][0]["score_components"]["production_value"] == 990
    assert errors == []
    assert decision["action_validation"]["mode"] == "disabled_for_replay_alignment"


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


def test_build_agent_decisions_can_report_strict_action_mismatch():
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
        {"action": [], "status": "ACTIVE", "observation": {}},
        {"action": [], "status": "ACTIVE", "observation": {}},
    ]

    _, errors = generate_rollouts.build_agent_decisions(
        step,
        ["main.py", "random"],
        action_step,
        validate_actions=True,
    )

    assert errors[0]["type"] == "action_mismatch"


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


def test_parse_args_defaults_use_versioned_rollout_paths(monkeypatch):
    monkeypatch.setattr("sys.argv", ["generate_rollouts.py"])

    args = generate_rollouts.parse_args()

    assert args.output_dir.as_posix() == f"data/rollouts_v2/{main.AGENT_VERSION}"
    assert args.summary.as_posix() == f"results/local_rollouts_{main.AGENT_VERSION}.json"
