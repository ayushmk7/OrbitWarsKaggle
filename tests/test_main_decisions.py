import math

import main


def make_obs(source_ships=20):
    return {
        "player": 0,
        "step": 12,
        "planets": [
            [1, 0, 0.0, 0.0, 1.0, source_ships, 3],
            [2, -1, 3.0, 4.0, 1.0, 5, 10],
            [3, -1, 10.0, 0.0, 1.0, 1, 4],
            [4, 1, 0.0, 20.0, 1.0, 8, 5],
        ],
        "fleets": [],
    }


def make_production_scoring_obs():
    return {
        "player": 0,
        "step": 100,
        "planets": [
            [1, 0, 0.0, 0.0, 1.0, 40, 3],
            [2, -1, 3.0, 4.0, 1.0, 1, 1],
            [3, -1, 20.0, 0.0, 1.0, 5, 8],
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
    assert decision["chosen_reason"] == "selected highest-scoring legal production target per owned planet"
    assert len(decision["chosen_candidate_ids"]) == 1

    chosen_id = decision["chosen_candidate_ids"][0]
    candidates = {candidate["candidate_id"]: candidate for candidate in decision["candidates"]}
    chosen = candidates[chosen_id]
    assert chosen["candidate_type"] == "expand"
    assert chosen["source_planet_id"] == 1
    assert chosen["target_planet_id"] == 2
    assert chosen["move"] == result["moves"][0]
    assert chosen["travel_turns"] == 4
    assert chosen["score"] == 4830
    assert chosen["score_components"]["production_value"] == 4840
    assert chosen["legal"] is True
    assert chosen["rejection_reason"] is None
    assert chosen["reason"] == "highest production-adjusted expansion score"


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


def test_production_scoring_can_choose_farther_high_production_target():
    result = main.decide_with_trace(make_production_scoring_obs())

    assert result["moves"] == [[1, 0.0, 6]]
    chosen_id = result["decision"]["chosen_candidate_ids"][0]
    candidates = {candidate["candidate_id"]: candidate for candidate in result["decision"]["candidates"]}
    chosen = candidates[chosen_id]
    assert chosen["target_planet_id"] == 3
    assert chosen["score_components"]["target_production"] == 8
    assert chosen["score_components"]["production_value"] > 0
    assert chosen["score_components"]["travel_turns"] > 0


def test_insufficient_ships_still_records_scored_rejected_candidates():
    obs = make_production_scoring_obs()
    obs["planets"][0][5] = 1

    result = main.decide_with_trace(obs)

    assert result["moves"] == []
    assert result["decision"]["chosen_candidate_ids"] == []
    assert len(result["decision"]["candidates"]) == 2
    assert all(candidate["legal"] is False for candidate in result["decision"]["candidates"])
    assert all(
        candidate["rejection_reason"] == "insufficient_source_ships"
        for candidate in result["decision"]["candidates"]
    )
    assert all("score" in candidate for candidate in result["decision"]["candidates"])
    assert all("score_components" in candidate for candidate in result["decision"]["candidates"])


def test_source_reserve_rejects_marginal_capture_that_drains_planet():
    obs = {
        "player": 0,
        "step": 490,
        "planets": [
            [1, 0, 0.0, 0.0, 1.0, 6, 4],
            [2, -1, 1.0, 0.0, 1.0, 5, 1],
        ],
        "fleets": [],
    }

    result = main.decide_with_trace(obs)

    assert result["moves"] == []
    candidate = result["decision"]["candidates"][0]
    assert candidate["legal"] is False
    assert candidate["rejection_reason"] == "reserve_too_low"
    assert candidate["score_components"]["reserve_penalty"] > 0


def test_sun_blocked_candidate_is_rejected_and_safe_target_is_chosen():
    obs = {
        "player": 0,
        "step": 100,
        "planets": [
            [1, 0, 20.0, 50.0, 1.0, 50, 3],
            [2, -1, 80.0, 50.0, 1.0, 1, 20],
            [3, -1, 20.0, 80.0, 1.0, 1, 3],
        ],
        "fleets": [],
    }

    result = main.decide_with_trace(obs)

    assert result["moves"] == [[1, math.pi / 2, 2]]
    candidates_by_target = {
        candidate["target_planet_id"]: candidate
        for candidate in result["decision"]["candidates"]
    }
    assert candidates_by_target[2]["legal"] is False
    assert candidates_by_target[2]["rejection_reason"] == "sun_blocked"
    assert candidates_by_target[3]["legal"] is True
    assert result["decision"]["chosen_candidate_ids"] == [candidates_by_target[3]["candidate_id"]]
