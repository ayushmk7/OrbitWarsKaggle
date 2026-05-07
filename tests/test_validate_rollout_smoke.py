from pathlib import Path

import validate_rollout_smoke


def write_jsonl(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def valid_rollout_jsonl(tmp_path):
    return write_jsonl(
        tmp_path / "rollout.jsonl",
        [
            (
                '{"type":"metadata","schema_version":2,'
                '"generator_version":"rollout_generator_v2_decision_trace",'
                '"agent_versions":["nearest_sniper_v2_traceable","builtin_random"],'
                '"run_started_at":"2026-01-01T00:00:00+00:00",'
                '"run_finished_at":"2026-01-01T00:00:01+00:00",'
                '"duration_ms":1000.0,'
                '"final_ship_scores":[14,12],'
                '"winner_agent_index":0,'
                '"errors":[]}'
            ),
            (
                '{"type":"step","schema_version":2,"agent_decisions":[{'
                '"agent_index":0,'
                '"agent_version":"nearest_sniper_v2_traceable",'
                '"runtime_ms":0.5,'
                '"error":null,'
                '"candidates":[{'
                '"candidate_id":"nearest_sniper_v2_traceable:t1:p1->p2:6",'
                '"candidate_type":"expand",'
                '"move":[1,0.9,6],'
                '"score":-5.0,'
                '"score_components":{"distance_penalty":-5.0},'
                '"legal":true,'
                '"rejection_reason":null,'
                '"reason":"nearest capturable non-owned planet from source 1"'
                '}],'
                '"chosen_candidate_ids":["nearest_sniper_v2_traceable:t1:p1->p2:6"],'
                '"chosen_moves":[[1,0.9,6]],'
                '"chosen_reason":"selected nearest legal capturable target per owned planet"'
                '}]}'
            ),
        ],
    )


def test_validate_rollout_smoke_accepts_valid_schema(tmp_path):
    result = validate_rollout_smoke.validate_rollout(valid_rollout_jsonl(tmp_path))

    assert result.ok is True
    assert result.schema_version == 2
    assert result.steps_checked == 1
    assert result.agent_decisions_found == 1
    assert result.candidates_found == 1
    assert result.metadata_errors == 0


def test_validate_rollout_smoke_rejects_missing_metadata_fields(tmp_path):
    path = write_jsonl(
        tmp_path / "rollout.jsonl",
        [
            '{"type":"metadata","schema_version":2}',
            '{"type":"step","schema_version":2,"agent_decisions":[]}',
        ],
    )

    result = validate_rollout_smoke.validate_rollout(path)

    assert result.ok is False
    assert "metadata missing generator_version" in result.errors


def test_validate_rollout_smoke_rejects_missing_candidates(tmp_path):
    path = write_jsonl(
        tmp_path / "rollout.jsonl",
        [
            (
                '{"type":"metadata","schema_version":2,'
                '"generator_version":"rollout_generator_v2_decision_trace",'
                '"agent_versions":[],"run_started_at":"x","run_finished_at":"x",'
                '"duration_ms":1,"final_ship_scores":[],"winner_agent_index":null,'
                '"errors":[]}'
            ),
            (
                '{"type":"step","schema_version":2,"agent_decisions":[{'
                '"agent_index":0,"agent_version":"v","runtime_ms":0,'
                '"error":null,"candidates":[],"chosen_candidate_ids":[],'
                '"chosen_moves":[],"chosen_reason":"none"}]}'
            ),
        ],
    )

    result = validate_rollout_smoke.validate_rollout(path)

    assert result.ok is False
    assert "no candidates found" in result.errors
