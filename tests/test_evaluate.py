import json
from pathlib import Path

import evaluate
import main


def fake_result(
    *,
    reward,
    winner_agent_index,
    final_ship_score,
    duration_ms,
    errors=None,
):
    return {
        "rewards": [reward, -reward if reward is not None else None],
        "winner_agent_index": winner_agent_index,
        "final_ship_scores": [final_ship_score, 100],
        "duration_ms": duration_ms,
        "errors": errors or [],
        "agent_versions": [main.AGENT_VERSION, "builtin_random"],
    }


def test_summarize_results_counts_outcomes_errors_and_averages():
    results = [
        fake_result(reward=1, winner_agent_index=0, final_ship_score=300, duration_ms=1000.0),
        fake_result(
            reward=-1,
            winner_agent_index=1,
            final_ship_score=120,
            duration_ms=2000.0,
            errors=[{"type": "runtime_error"}, {"type": "invalid_action"}],
        ),
        fake_result(reward=0, winner_agent_index=None, final_ship_score=180, duration_ms=3000.0),
    ]

    summary = evaluate.summarize_results(
        results=results,
        agents=["main.py", "random"],
        start_seed=7,
        games=3,
        opponents=["random"],
        generated_at="2026-01-01T00:00:00+00:00",
    )

    assert summary["generated_at"] == "2026-01-01T00:00:00+00:00"
    assert summary["agent_version"] == main.AGENT_VERSION
    assert summary["agents"] == ["main.py", "random"]
    assert summary["opponents"] == ["random"]
    assert summary["start_seed"] == 7
    assert summary["games"] == 3
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["ties"] == 1
    assert summary["win_rate"] == 1 / 3
    assert summary["average_reward"] == 0
    assert summary["average_final_ship_score"] == 200
    assert summary["average_duration_ms"] == 2000
    assert summary["error_count"] == 2
    assert summary["results"] == results


def test_parse_args_defaults_use_agent_versioned_paths(monkeypatch):
    monkeypatch.setattr("sys.argv", ["evaluate.py"])

    args = evaluate.parse_args()

    assert args.start_seed == 1
    assert args.games == 20
    assert args.opponents == "random"
    assert args.summary.as_posix() == f"results/quick_{main.AGENT_VERSION}.json"
    assert args.output_dir.as_posix() == f"data/rollouts_v2/{main.AGENT_VERSION}"


def test_parse_args_accepts_explicit_values(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate.py",
            "--start-seed",
            "10",
            "--games",
            "5",
            "--opponents",
            "random,main.py",
            "--summary",
            "results/custom.json",
            "--output-dir",
            "data/custom",
        ],
    )

    args = evaluate.parse_args()

    assert args.start_seed == 10
    assert args.games == 5
    assert args.opponents == "random,main.py"
    assert args.summary == Path("results/custom.json")
    assert args.output_dir == Path("data/custom")


def test_run_evaluation_generates_seeded_rollouts_and_writes_summary(tmp_path, monkeypatch):
    calls = []

    def fake_generate_rollout(seed, agents, output_dir):
        calls.append((seed, agents, output_dir))
        return fake_result(
            reward=1 if seed == 3 else -1,
            winner_agent_index=0 if seed == 3 else 1,
            final_ship_score=100 + seed,
            duration_ms=1000.0 + seed,
        )

    monkeypatch.setattr(evaluate.generate_rollouts, "generate_rollout", fake_generate_rollout)
    summary_path = tmp_path / "results" / "summary.json"
    output_dir = tmp_path / "data"

    summary = evaluate.run_evaluation(
        start_seed=3,
        games=2,
        opponents=["random"],
        summary_path=summary_path,
        output_dir=output_dir,
    )

    assert calls == [
        (3, ["main.py", "random"], output_dir),
        (4, ["main.py", "random"], output_dir),
    ]
    assert summary["games"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["ties"] == 0
    assert summary["error_count"] == 0
    assert json.loads(summary_path.read_text(encoding="utf-8")) == summary

