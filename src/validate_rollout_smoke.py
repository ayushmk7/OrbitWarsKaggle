"""Validate that a rollout JSONL file has the schema v2 DPO trace shape."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


METADATA_FIELDS = {
    "generator_version",
    "agent_versions",
    "run_started_at",
    "run_finished_at",
    "duration_ms",
    "final_ship_scores",
    "winner_agent_index",
    "errors",
}

DECISION_FIELDS = {
    "agent_version",
    "runtime_ms",
    "error",
    "candidates",
    "chosen_candidate_ids",
    "chosen_moves",
    "chosen_reason",
}

CANDIDATE_FIELDS = {
    "candidate_id",
    "candidate_type",
    "move",
    "score",
    "score_components",
    "legal",
    "rejection_reason",
    "reason",
}


@dataclass
class SmokeValidationResult:
    ok: bool
    schema_version: int | None = None
    steps_checked: int = 0
    agent_decisions_found: int = 0
    candidates_found: int = 0
    metadata_errors: int = 0
    errors: list[str] = field(default_factory=list)


def _load_json_lines(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_number} is not valid JSON: {exc}") from exc
    return records


def _missing_fields(record: dict[str, Any], fields: set[str]) -> list[str]:
    return sorted(field for field in fields if field not in record)


def validate_rollout(path: Path) -> SmokeValidationResult:
    errors = []
    try:
        records = _load_json_lines(path)
    except (OSError, ValueError) as exc:
        return SmokeValidationResult(ok=False, errors=[str(exc)])

    if not records:
        return SmokeValidationResult(ok=False, errors=["file has no records"])

    metadata = records[0]
    schema_version = metadata.get("schema_version")
    if metadata.get("type") != "metadata":
        errors.append("first record is not metadata")
    if schema_version != 2:
        errors.append("metadata schema_version is not 2")

    for field_name in _missing_fields(metadata, METADATA_FIELDS):
        errors.append(f"metadata missing {field_name}")

    metadata_errors = len(metadata.get("errors", [])) if isinstance(metadata.get("errors"), list) else 0
    steps_checked = 0
    agent_decisions_found = 0
    candidates_found = 0

    for record in records[1:]:
        if record.get("type") != "step":
            continue
        steps_checked += 1
        for decision in record.get("agent_decisions", []):
            if decision.get("agent_index") != 0:
                continue
            agent_decisions_found += 1
            for field_name in _missing_fields(decision, DECISION_FIELDS):
                errors.append(f"decision missing {field_name}")
            for candidate in decision.get("candidates", []):
                candidates_found += 1
                for field_name in _missing_fields(candidate, CANDIDATE_FIELDS):
                    errors.append(f"candidate missing {field_name}")

    if steps_checked == 0:
        errors.append("no step records found")
    if agent_decisions_found == 0:
        errors.append("no agent_index 0 decisions found")
    if candidates_found == 0:
        errors.append("no candidates found")

    return SmokeValidationResult(
        ok=not errors,
        schema_version=schema_version,
        steps_checked=steps_checked,
        agent_decisions_found=agent_decisions_found,
        candidates_found=candidates_found,
        metadata_errors=metadata_errors,
        errors=errors,
    )


def print_result(result: SmokeValidationResult) -> None:
    print(f"Schema version: {result.schema_version}")
    print(f"Steps checked: {result.steps_checked}")
    print(f"Agent decisions found: {result.agent_decisions_found}")
    print(f"Candidates found: {result.candidates_found}")
    print(f"Metadata errors: {result.metadata_errors}")
    for error in result.errors:
        print(f"Error: {error}")
    print(f"Smoke validation: {'PASS' if result.ok else 'FAIL'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rollout_jsonl", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = validate_rollout(args.rollout_jsonl)
    print_result(result)
    raise SystemExit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
