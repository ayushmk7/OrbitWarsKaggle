import math

import main


def make_obs(source_ships=20):
    return {
        "player": 0,
        "step": 12,
        "planets": [
            [1, 0, 0.0, 0.0, 1.0, source_ships, 3],
            [2, -1, 3.0, 4.0, 1.0, 5, 2],
            [3, -1, 10.0, 0.0, 1.0, 1, 4],
            [4, 1, 0.0, 20.0, 1.0, 8, 5],
        ],
        "fleets": [],
    }


def test_agent_returns_raw_moves_for_existing_strategy():
    assert main.agent(make_obs()) == [[1, math.atan2(4.0, 3.0), 6]]


def test_decide_with_trace_records_candidates_scores_and_chosen_reason():
    result = main.decide_with_trace(make_obs())
    decision = result["decision"]

    assert result["moves"] == [[1, math.atan2(4.0, 3.0), 6]]
    assert decision["agent_version"] == main.AGENT_VERSION
    assert decision["runtime_ms"] >= 0
    assert decision["error"] is None
    assert decision["chosen_moves"] == result["moves"]
    assert decision["chosen_reason"] == "selected nearest legal capturable target per owned planet"
    assert len(decision["chosen_candidate_ids"]) == 1

    chosen_id = decision["chosen_candidate_ids"][0]
    candidates = {candidate["candidate_id"]: candidate for candidate in decision["candidates"]}
    chosen = candidates[chosen_id]
    assert chosen["candidate_type"] == "expand"
    assert chosen["source_planet_id"] == 1
    assert chosen["target_planet_id"] == 2
    assert chosen["move"] == result["moves"][0]
    assert chosen["score"] == -5.0
    assert chosen["score_components"]["distance_penalty"] == -5.0
    assert chosen["legal"] is True
    assert chosen["rejection_reason"] is None
    assert chosen["reason"] == "nearest capturable non-owned planet from source 1"


def test_decide_with_trace_records_rejections_when_source_lacks_ships():
    result = main.decide_with_trace(make_obs(source_ships=1))
    decision = result["decision"]

    assert result["moves"] == []
    assert decision["chosen_candidate_ids"] == []
    assert decision["chosen_moves"] == []
    assert all(
        candidate["rejection_reason"] == "insufficient_source_ships"
        for candidate in decision["candidates"]
    )


def test_decide_with_trace_has_no_candidates_when_no_targets_exist():
    obs = {
        "player": 0,
        "step": 3,
        "planets": [[1, 0, 0.0, 0.0, 1.0, 20, 3]],
        "fleets": [],
    }

    result = main.decide_with_trace(obs)

    assert result["moves"] == []
    assert result["decision"]["candidates"] == []
    assert result["decision"]["chosen_candidate_ids"] == []
