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
    moves = main.agent(make_obs())

    assert moves
    assert all(isinstance(move, list) for move in moves)
    assert all(len(move) == 3 for move in moves)


def test_decide_with_trace_records_candidates_scores_and_chosen_reason():
    result = main.decide_with_trace(make_obs())
    decision = result["decision"]

    assert result["moves"]
    assert decision["agent_version"] == main.AGENT_VERSION
    assert decision["runtime_ms"] >= 0
    assert decision["error"] is None
    assert decision["chosen_moves"] == result["moves"]
    assert decision["chosen_reason"] == "selected budgeted production-scored legal targets"
    assert decision["chosen_candidate_ids"]

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


def test_decide_with_trace_uses_observation_step_in_candidate_id_and_scoring():
    result = main.decide_with_trace(make_obs())
    candidate = result["decision"]["candidates"][0]

    assert ":t12:" in candidate["candidate_id"]
    assert candidate["score_components"]["remaining_after_arrival"] == 484


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

    assert [1, 0.0, 6] in result["moves"]
    candidates = {candidate["candidate_id"]: candidate for candidate in result["decision"]["candidates"]}
    chosen_targets = [
        candidates[chosen_id]["target_planet_id"]
        for chosen_id in result["decision"]["chosen_candidate_ids"]
    ]
    assert 3 in chosen_targets
    chosen = next(candidate for candidate in candidates.values() if candidate["target_planet_id"] == 3)
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


def test_desired_reserve_is_phase_aware():
    valuable = main.Planet(1, 0, 0.0, 0.0, 1.0, 50, 8)
    low_value = main.Planet(2, 0, 0.0, 0.0, 1.0, 50, 2)

    assert main._desired_reserve(valuable, step=20, score=100) == 8
    assert main._desired_reserve(low_value, step=20, score=100) == 3
    assert main._desired_reserve(valuable, step=250, score=100) == 8
    assert main._desired_reserve(low_value, step=250, score=100) == 3
    assert main._desired_reserve(valuable, step=450, score=100) == 4
    assert main._desired_reserve(valuable, step=450, score=-1) == 8


def test_candidates_include_budget_trace_fields():
    result = main.decide_with_trace(make_obs())
    candidate = result["decision"]["candidates"][0]

    assert "source_budget_before" in candidate
    assert "source_budget_after" in candidate
    assert "desired_reserve" in candidate
    assert candidate["score_components"]["game_phase"] == "early"
    assert "preliminary_score" in candidate["score_components"]
    assert "base_reserve" in candidate["score_components"]


def candidate_for_budget(candidate_id, ships, score, budget=10, reserve=2, legal=True):
    return {
        "candidate_id": candidate_id,
        "move": [1, 0.0, ships],
        "ships": ships,
        "score": score,
        "legal": legal,
        "rejection_reason": None if legal else "preexisting_rejection",
        "source_budget_before": budget,
        "source_budget_after": budget - ships,
        "desired_reserve": reserve,
    }


def test_select_budgeted_candidates_accepts_multiple_until_budget_exhausted():
    candidates = [
        candidate_for_budget("a", ships=4, score=100),
        candidate_for_budget("b", ships=3, score=90),
        candidate_for_budget("c", ships=3, score=80),
    ]

    selected = main._select_budgeted_candidates(candidates)

    assert [candidate["candidate_id"] for candidate in selected] == ["a", "b"]
    assert candidates[0]["source_budget_after"] == 6
    assert candidates[1]["source_budget_after"] == 3
    assert candidates[2]["legal"] is False
    assert candidates[2]["rejection_reason"] == "source_budget_exhausted"


def test_select_budgeted_candidates_rejects_non_positive_scores():
    candidates = [
        candidate_for_budget("a", ships=2, score=0),
        candidate_for_budget("b", ships=2, score=-5),
    ]

    selected = main._select_budgeted_candidates(candidates)

    assert selected == []
    assert [candidate["rejection_reason"] for candidate in candidates] == [
        "non_positive_score",
        "non_positive_score",
    ]


def test_agent_can_choose_multiple_budgeted_moves_from_one_source():
    obs = {
        "player": 0,
        "step": 120,
        "planets": [
            [1, 0, 0.0, 0.0, 1.0, 30, 3],
            [2, -1, 5.0, 0.0, 1.0, 2, 8],
            [3, -1, 0.0, 6.0, 1.0, 2, 7],
            [4, -1, 10.0, 0.0, 1.0, 20, 1],
        ],
        "fleets": [],
    }

    result = main.decide_with_trace(obs)

    assert len(result["moves"]) == 2
    assert sum(move[2] for move in result["moves"]) == 6
    assert result["decision"]["chosen_reason"] == "selected budgeted production-scored legal targets"
    chosen_targets = {
        candidate["target_planet_id"]
        for candidate in result["decision"]["candidates"]
        if candidate["candidate_id"] in result["decision"]["chosen_candidate_ids"]
    }
    assert chosen_targets == {2, 3}


def test_agent_caps_multiple_profitable_moves_by_source_budget():
    obs = {
        "player": 0,
        "step": 120,
        "planets": [
            [1, 0, 0.0, 0.0, 1.0, 10, 3],
            [2, -1, 5.0, 0.0, 1.0, 2, 8],
            [3, -1, 0.0, 6.0, 1.0, 2, 7],
            [4, -1, 8.0, 0.0, 1.0, 2, 6],
        ],
        "fleets": [],
    }

    result = main.decide_with_trace(obs)

    source_spend = sum(move[2] for move in result["moves"] if move[0] == 1)
    assert source_spend <= 7
    assert len(result["moves"]) == 2
    rejected = [
        candidate
        for candidate in result["decision"]["candidates"]
        if candidate["rejection_reason"] == "source_budget_exhausted"
    ]
    assert rejected


def test_valuable_midgame_source_keeps_reserve():
    obs = {
        "player": 0,
        "step": 250,
        "planets": [
            [1, 0, 0.0, 0.0, 1.0, 12, 8],
            [2, -1, 5.0, 0.0, 1.0, 3, 8],
            [3, -1, 0.0, 6.0, 1.0, 3, 7],
        ],
        "fleets": [],
    }

    result = main.decide_with_trace(obs)

    source_spend = sum(move[2] for move in result["moves"] if move[0] == 1)
    assert source_spend <= 4
    assert len(result["moves"]) == 1
    assert any(
        candidate["rejection_reason"] == "reserve_too_low"
        for candidate in result["decision"]["candidates"]
    )


def test_budgeting_preserves_sun_blocked_and_insufficient_ship_reasons():
    obs = {
        "player": 0,
        "step": 100,
        "planets": [
            [1, 0, 20.0, 50.0, 1.0, 2, 3],
            [2, -1, 80.0, 50.0, 1.0, 5, 20],
            [3, -1, 20.0, 80.0, 1.0, 5, 3],
        ],
        "fleets": [],
    }

    result = main.decide_with_trace(obs)
    candidates_by_target = {
        candidate["target_planet_id"]: candidate
        for candidate in result["decision"]["candidates"]
    }

    assert candidates_by_target[2]["rejection_reason"] == "sun_blocked"
    assert candidates_by_target[3]["rejection_reason"] == "insufficient_source_ships"
