# Orbit Wars Next Steps To Submission

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current traceable nearest-planet baseline into a validated, submission-ready Orbit Wars agent and run the Kaggle submission feedback loop.

**Architecture:** Keep `main.py` as the Kaggle entrypoint. Add focused helper modules only when they improve correctness or testability, then either submit a `submission.tar.gz` containing those files or inline the final stable logic back into `main.py`. Use local rollouts and Kaggle replays as evidence before promoting strategy changes.

**Tech Stack:** Python, `kaggle-environments`, Kaggle CLI, `pytest`, JSON/JSONL rollout artifacts.

---

## Current State

- `main.py` is a valid Kaggle entrypoint with `agent(obs)` and `decide_with_trace(obs)`.
- Current agent version is `nearest_sniper_v2_traceable`.
- `generate_rollouts.py` can create rollout JSONL files and metadata summaries.
- Tests exist for decision tracing and rollout metadata.
- `results/local_rollouts_v2_smoke.json` records zero rollout trace errors after action-alignment fixes.
- `geometry.py` must match the installed Kaggle environment physics before further strategy tuning; in particular, fleet speed uses the `** 1.5` log curve from `README.md` and the environment source.
- `prediction.py` contains initial-position orbit prediction and approximate intercept sampling for orbit-aware targeting.
- `main.py` now uses phase-aware reserves, per-source budgeted move selection, and candidate budget trace fields.
- `plan.md` defines the long-term direction: strong rule-based agent first, optional DPO candidate ranking later.
- `.gitignore` ignores only local caches, Python bytecode, virtual environments, and `submission.tar.gz`; generated evidence directories remain trackable.

## Submission Policy

- Submit only code needed by the runtime agent.
- Do not submit API keys, judge scripts, or exploratory notebooks.
- Keep rollout data, replay logs, competition downloads, and benchmark summaries in the repository so strategy changes can be audited from the same evidence later.
- Do not depend on network calls, Kaggle CLI, local files, or environment secrets from `main.py`.
- Promote a new agent version only when it beats the previous version on fixed held-out seeds or fixes a verified replay failure without a broader regression.
- Prefer simple deterministic rule logic until the evaluation harness is reliable.

---

## Task 1: Fix Rollout Trace Validation

**Status:** Implemented. `generate_rollouts.py` records the exact `main.py` decision used during `env.run(...)`, falls back to recomputation only when a recorded decision is unavailable, and keeps action validation disabled by default for replay alignment. Strict mismatch detection remains available through `validate_actions=True`.

**Files:**
- Modify: `generate_rollouts.py`
- Test: `tests/test_generate_rollouts.py`
- Inspect: `results/local_rollouts_v2_smoke.json`

- [ ] **Step 1: Reproduce the current mismatch**

Run:

```bash
pytest tests/test_generate_rollouts.py tests/test_main_decisions.py -q
python generate_rollouts.py --start-seed 1 --games 1 --output-dir data/rollouts_v2_smoke --summary results/local_rollouts_v2_smoke.json
```

Expected before the Task 1 fix: tests pass, but the generated summary contains `action_mismatch` entries for `main.py`. Current fixed summaries should keep `errors` empty.

- [ ] **Step 2: Identify the correct action timing**

Inspect how `kaggle_environments` records actions in `env.run(...)`. Determine whether a step's `action` belongs to the same observation step, the next step, or a post-transition record.

Acceptance criteria:

- `build_agent_decisions(...)` compares `decide_with_trace(observation)["moves"]` with the actual action produced for that same observation.
- The comparison does not flag mismatches caused only by step indexing.

- [ ] **Step 3: Add a regression test for no false mismatch**

Update or add a test that simulates the correct step/action relationship.

Expected assertion:

```python
_, errors = generate_rollouts.build_agent_decisions(step, ["main.py", "random"], action_step)
assert errors == []
```

- [ ] **Step 4: Regenerate smoke rollout**

Run:

```bash
python generate_rollouts.py --start-seed 1 --games 1 --output-dir data/rollouts_v2_smoke --summary results/local_rollouts_v2_smoke.json
```

Expected:

- `results/local_rollouts_v2_smoke.json` has zero false `action_mismatch` errors.
- Any remaining errors represent real runtime or action problems.

- [ ] **Step 5: Commit**

```bash
git add generate_rollouts.py tests/test_generate_rollouts.py results/local_rollouts_v2_smoke.json
git commit -m "fix rollout action trace validation"
```

---

## Task 2: Track Generated Artifacts

**Status:** Implemented. Generated evidence folders remain visible to git, and `submission.tar.gz` is ignored by default unless explicitly force-added for a reproducible submission artifact.

**Files:**
- Modify: `.gitignore`
- Track rollout JSONL, replay logs, local competition downloads, and benchmark summaries when they support agent comparisons or debugging.

- [ ] **Step 1: Decide what stays in git**

Keep source files, tests, docs, rollout JSONL, replays, logs, local competition downloads, and benchmark summaries. The only generated files to ignore by default are local caches, Python bytecode, virtual environments, and submission bundles.

- [ ] **Step 2: Update `.gitignore`**

Keep generated evidence directories out of `.gitignore`. `.gitignore` should not ignore `data/`, `results/`, `replays/`, `logs/`, or `orbit-wars-data/`.

Use:

```gitignore
.venv/
__pycache__/
*.py[cod]
submission.tar.gz
```

If `submission.tar.gz` is useful as a reproducibility artifact for a specific submission, add it explicitly with `git add -f submission.tar.gz`.

- [ ] **Step 3: Check current tracked/generated files**

Run:

```bash
git status --short
git ls-files data results replays logs orbit-wars-data 2>/dev/null
```

Expected: generated evidence files are visible to git when present, and only local caches or submission bundles are ignored.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "track generated rollout evidence"
```

---

## Task 3: Build A Real Evaluation Command

**Status:** Implemented. `evaluate.py` can run fixed seed ranges, write JSON summaries, and report wins, losses, ties, win rate, reward, final ship score, duration, errors, agent version, opponents, and seed range.

**Files:**
- Create: `evaluate.py`
- Test: `tests/test_evaluate.py`
- Reuse: `generate_rollouts.py`

- [ ] **Step 1: Add summary metrics**

Create an evaluator that can run a seed range and report:

- games
- wins
- losses
- ties
- win rate
- average reward
- average final ship score
- average duration
- error count
- agent version
- opponent list
- seed range

- [ ] **Step 2: Keep command-line usage simple**

Target command:

```bash
python evaluate.py --start-seed 1 --games 20 --opponents random --summary results/quick_nearest_sniper_v2_traceable.json
```

Expected output:

```text
Agent version: nearest_sniper_v2_traceable
Games: 20
Wins: an integer from 0 through 20
Win rate: a decimal from 0.000 through 1.000
Errors: 0
Summary: results/quick_nearest_sniper_v2_traceable.json
```

- [ ] **Step 3: Add tests for metric aggregation**

Use small fake `generate_rollout(...)`-style result dictionaries. Test win/loss/tie counting, average ship score, and error counting without running the full Kaggle environment.

- [ ] **Step 4: Run quick evaluation**

Run:

```bash
pytest tests/test_evaluate.py tests/test_generate_rollouts.py tests/test_main_decisions.py -q
python evaluate.py --start-seed 1 --games 20 --opponents random --summary results/quick_nearest_sniper_v2_traceable.json
```

Expected: tests pass and the summary file records the current baseline performance.

- [ ] **Step 5: Commit**

```bash
git add evaluate.py tests/test_evaluate.py results/quick_nearest_sniper_v2_traceable.json
git commit -m "add local evaluation summary command"
```

---

## Task 4: Add Geometry And Safety Helpers

**Status:** Implemented for static geometry and sun safety. `geometry.py` owns distance, angle, fleet speed, travel turns, circle intersection, and sun-shot checks. Orbit prediction now lives in `prediction.py` instead of `geometry.py`.

**Files:**
- Create: `geometry.py`
- Test: `tests/test_geometry.py`
- Modify later: `main.py`

- [ ] **Step 1: Implement pure helpers**

Add:

- `distance_xy(ax, ay, bx, by)`
- `angle_to_xy(ax, ay, bx, by)`
- `fleet_speed(ships, max_speed=6.0)`
- `turns_to_reach(distance, ships, max_speed=6.0)`
- `segment_intersects_circle(ax, ay, bx, by, cx, cy, radius)`
- `shot_hits_sun(source, target, sun_x=50.0, sun_y=50.0, sun_radius=10.0)`

- [ ] **Step 2: Test geometry**

Cover:

- horizontal, vertical, and diagonal angles
- fleet speed increases with ship count and matches the Kaggle environment `** 1.5` log curve
- shots through `(50, 50)` hit the sun
- off-center shots do not hit the sun
- tangent or near-tangent behavior is deterministic

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_geometry.py -q
```

- [ ] **Step 4: Commit**

```bash
git add geometry.py tests/test_geometry.py
git commit -m "add orbit wars geometry helpers"
```

---

## Task 5: Upgrade Expansion Scoring

**Status:** Implemented and repaired. `decide_with_trace(obs)` now uses `obs["step"]`, records every selected and rejected candidate in `decision["candidates"]`, preserves raw move output from `agent(obs)`, and scores targets by production value, ship cost, travel time, reserve pressure, and remaining turns.

**Files:**
- Modify: `main.py`
- Test: `tests/test_main_decisions.py`
- Use: `geometry.py`

- [ ] **Step 1: Replace nearest-only scoring**

Score non-owned targets with production value, travel time, ships required, remaining turns, and reserve left.

Minimum scoring shape:

```python
remaining_after_arrival = max(0, 500 - step - travel_turns)
value = target.production * remaining_after_arrival
cost = ships_needed + travel_turns
reserve_penalty = max(0, desired_reserve - source_reserve_after)
score = value - cost - reserve_penalty
```

- [ ] **Step 2: Preserve traceability**

Each candidate should keep:

- `candidate_id`
- `candidate_type`
- `move`
- `source_planet_id`
- `target_planet_id`
- `ships`
- `angle`
- `distance`
- `travel_turns`
- `score`
- `score_components`
- `legal`
- `rejection_reason`
- `reason`

- [ ] **Step 3: Add behavior tests**

Add tests proving:

- a farther high-production neutral can beat a nearer low-production neutral
- insufficient ships still produce rejected candidates
- source reserve prevents draining a planet for marginal captures
- `agent(obs)` still returns raw move lists only

- [ ] **Step 4: Run quick benchmark**

```bash
pytest tests/test_main_decisions.py tests/test_geometry.py -q
python evaluate.py --start-seed 1 --games 20 --opponents random --summary results/quick_production_expansion.json
```

Promotion criterion: do not replace the default behavior if win rate or final ship score regresses badly against the previous quick summary.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main_decisions.py results/quick_production_expansion.json
git commit -m "score expansion by production value"
```

---

## Task 6: Add Sun-Safe Candidate Filtering

**Status:** Implemented. Static direct-shot candidates that cross the sun remain in traces with `legal == False` and `rejection_reason == "sun_blocked"`. Sun-blocked rejection is preserved ahead of budget/selection rejections.

**Files:**
- Modify: `main.py`
- Test: `tests/test_main_decisions.py`
- Use: `geometry.py`

- [ ] **Step 1: Mark sun-blocked candidates illegal**

Use `shot_hits_sun(...)` before choosing a move. Keep the candidate in traces with:

```python
"legal": False,
"rejection_reason": "sun_blocked"
```

- [ ] **Step 2: Add tests**

Create an observation where the nearest or highest-scoring target is behind the sun and another legal target exists. Assert the agent rejects the blocked shot and chooses the safe target.

- [ ] **Step 3: Benchmark**

```bash
pytest tests/test_main_decisions.py tests/test_geometry.py -q
python evaluate.py --start-seed 1 --games 50 --opponents random --summary results/quick_sun_safe.json
```

Expected: zero invalid/sun-blocked self-inflicted choices in inspected traces.

- [ ] **Step 4: Commit**

```bash
git add main.py tests/test_main_decisions.py results/quick_sun_safe.json
git commit -m "avoid sun-blocked launches"
```

---

## Task 7: Add Ship Budgeting And Overcommit Control

**Goal:** Prevent the agent from draining a source planet across multiple good-looking launches, while still allowing one strong planet to make more than one profitable capture when it has enough surplus ships.

**Prerequisite:** `geometry.fleet_speed(...)` and `turns_to_reach(...)` must match the installed Kaggle environment formula before tuning source budgets. If this has not been corrected yet, fix it and refresh the quick benchmark first.

**Why this matters now:** Task 5 made candidate scoring production-aware, and Task 6 made unsafe sun shots illegal. The next failure mode is allocation: if selection later allows multiple accepted candidates from one source, each candidate can look legal in isolation but the combined moves can over-spend the same source planet. Task 7 makes budgeting explicit and traceable before adding defense, orbit prediction, or richer candidate generation.

**Files:**
- Modify: `main.py`
- Test: `tests/test_main_decisions.py`
- Benchmark output: `results/quick_budgeting.json`

**Important current code shape:**
- `decide_with_trace(obs)` builds `source_candidates` for each owned planet.
- Each candidate already has `ships`, `score`, `legal`, `rejection_reason`, and `score_components`.
- Current code chooses only one best legal candidate per source, so it does not yet spend from a source budget across multiple accepted moves.
- This task should make source budgeting reusable for future tasks that may choose multiple moves per source.

**Behavior contract after Task 7:**
- Every candidate still appears in `decision["candidates"]`.
- `agent(obs)` still returns only raw move lists.
- Candidate trace data includes budget fields so bad choices can be debugged from rollout JSONL.
- A source planet never sends more ships than its available budget after reserve.
- Multiple candidates from the same source are considered in descending `score`.
- Candidates that no longer fit the remaining source budget are rejected with `rejection_reason == "source_budget_exhausted"`.
- Candidates rejected because they would violate reserve are rejected with `rejection_reason == "reserve_too_low"`.
- Existing rejection reasons from earlier tasks remain valid: `sun_blocked`, `insufficient_source_ships`, and `not_highest_scoring_target_for_source` should not disappear unless replaced intentionally by budget-specific reasons.

**Status:** Implemented with `_game_phase(...)`, `_desired_reserve(...)`, and `_select_budgeted_candidates(...)` in `main.py`.

Actual trace additions:

- top-level candidate fields: `source_budget_before`, `source_budget_after`, `desired_reserve`
- `score_components` fields: `game_phase`, `preliminary_score`, `base_reserve`
- preserved rejection reasons: `sun_blocked`, `insufficient_source_ships`
- budget rejection reasons: `non_positive_score`, `reserve_too_low`, `source_budget_exhausted`

Actual selection behavior:

- considers candidates per source in descending score order
- can choose multiple candidates per source
- caps selected moves per source with `MAX_MOVES_PER_SOURCE`
- never selects moves that violate the phase-aware reserve rule
- sets `decision["chosen_reason"]` to `selected budgeted production-scored legal targets`

### Task 7.1: Define Phase-Aware Reserve Rules

- [ ] **Step 1: Add helper constants near `AGENT_VERSION` in `main.py`**

Use named constants instead of magic numbers so future tuning can compare versions clearly.

```python
MAX_TURNS = 500
EARLY_GAME_END = 150
LATE_GAME_START = 400
MIN_PROFITABLE_SCORE = 0
```

- [ ] **Step 2: Add `_game_phase(step)` below `_candidate_id(...)`**

```python
def _game_phase(step):
    if step < EARLY_GAME_END:
        return "early"
    if step >= LATE_GAME_START:
        return "late"
    return "mid"
```

- [ ] **Step 3: Add `_desired_reserve(source, step, score)` below `_game_phase(...)`**

This codifies the phase-aware reserve policy:
- early game: keep at least 3 ships or one turn of production
- midgame: keep at least 5 ships on valuable planets
- late game: allow more spending for positive final-score launches, but never drain to zero by default

```python
def _desired_reserve(source, step, score):
    phase = _game_phase(step)
    production = max(0, source.production)

    if phase == "early":
        return max(3, production)

    if phase == "mid":
        if production >= 5:
            return max(5, production)
        return max(3, production)

    if score > MIN_PROFITABLE_SCORE:
        return max(1, production // 2)
    return max(3, production)
```

- [ ] **Step 4: Add tests for the reserve helper**

Append tests to `tests/test_main_decisions.py`. Use `main.Planet` so tests match the fallback/real namedtuple field names.

```python
def test_desired_reserve_is_phase_aware():
    valuable = main.Planet(1, 0, 0.0, 0.0, 1.0, 50, 8)
    low_value = main.Planet(2, 0, 0.0, 0.0, 1.0, 50, 2)

    assert main._desired_reserve(valuable, step=20, score=100) == 8
    assert main._desired_reserve(low_value, step=20, score=100) == 3
    assert main._desired_reserve(valuable, step=250, score=100) == 8
    assert main._desired_reserve(low_value, step=250, score=100) == 3
    assert main._desired_reserve(valuable, step=450, score=100) == 4
    assert main._desired_reserve(valuable, step=450, score=-1) == 8
```

- [ ] **Step 5: Run the new reserve-helper test and confirm it fails first**

```bash
python -m pytest tests/test_main_decisions.py::test_desired_reserve_is_phase_aware -q
```

Expected before implementation: fail with `AttributeError: module 'main' has no attribute '_desired_reserve'`.

- [ ] **Step 6: Implement the constants and helper functions**

Add the constants and helpers exactly as described above, then rerun:

```bash
python -m pytest tests/test_main_decisions.py::test_desired_reserve_is_phase_aware -q
```

Expected after implementation: pass.

### Task 7.2: Add Budget Fields To Candidate Traces

- [ ] **Step 1: Replace hardcoded reserve calculation in candidate generation**

Current Task 5 logic computes reserve before score with:

```python
desired_reserve = max(1, mine.production)
```

Change the candidate-building flow so it first computes a score with a provisional reserve, then uses `_desired_reserve(...)` for the actual budget decision.

Recommended minimal structure:

```python
base_reserve = max(1, mine.production)
base_reserve_penalty = max(0, base_reserve - source_reserve_after)
production_value = target.production * remaining_after_arrival
ship_cost = ships_needed
travel_cost = travel_turns
preliminary_score = production_value - ship_cost - travel_cost - base_reserve_penalty
desired_reserve = _desired_reserve(mine, step, preliminary_score)
reserve_penalty = max(0, desired_reserve - source_reserve_after)
score = production_value - ship_cost - travel_cost - reserve_penalty
```

- [ ] **Step 2: Add trace fields to each candidate**

At the top level of each candidate, add:

```python
"source_budget_before": mine.ships,
"source_budget_after": mine.ships - ships_needed,
"desired_reserve": desired_reserve,
```

Inside `score_components`, keep the existing reserve fields and add:

```python
"game_phase": _game_phase(step),
"preliminary_score": preliminary_score,
"base_reserve": base_reserve,
```

- [ ] **Step 3: Add a test proving budget fields exist**

```python
def test_candidates_include_budget_trace_fields():
    result = main.decide_with_trace(make_obs())
    candidate = result["decision"]["candidates"][0]

    assert "source_budget_before" in candidate
    assert "source_budget_after" in candidate
    assert "desired_reserve" in candidate
    assert candidate["score_components"]["game_phase"] == "early"
    assert "preliminary_score" in candidate["score_components"]
    assert "base_reserve" in candidate["score_components"]
```

- [ ] **Step 4: Run the budget trace test and confirm it fails first**

```bash
python -m pytest tests/test_main_decisions.py::test_candidates_include_budget_trace_fields -q
```

Expected before implementation: fail because the new trace fields do not exist.

- [ ] **Step 5: Implement the trace fields and rerun**

```bash
python -m pytest tests/test_main_decisions.py::test_candidates_include_budget_trace_fields -q
```

Expected after implementation: pass.

### Task 7.3: Select Moves With Per-Source Budgets

- [ ] **Step 1: Add `_select_budgeted_candidates(source_candidates)` below `_desired_reserve(...)`**

This helper should accept all candidates for one source planet, consider legal candidates by descending score, and mutate candidates only through trace fields/rejection reasons. Keeping it as a helper makes the allocation behavior testable without a full game observation.

```python
def _select_budgeted_candidates(source_candidates):
    if not source_candidates:
        return []

    source_budget = source_candidates[0]["source_budget_before"]
    selected = []

    for candidate in sorted(source_candidates, key=lambda item: item["score"], reverse=True):
        candidate["source_budget_before"] = source_budget
        candidate["source_budget_after"] = source_budget - candidate["ships"]

        if not candidate["legal"]:
            continue

        if candidate["score"] <= MIN_PROFITABLE_SCORE:
            candidate["legal"] = False
            candidate["rejection_reason"] = "non_positive_score"
            continue

        if candidate["ships"] > source_budget:
            candidate["legal"] = False
            candidate["rejection_reason"] = "source_budget_exhausted"
            continue

        if source_budget - candidate["ships"] < candidate["desired_reserve"]:
            candidate["legal"] = False
            candidate["rejection_reason"] = "reserve_too_low"
            continue

        selected.append(candidate)
        source_budget -= candidate["ships"]
        candidate["source_budget_after"] = source_budget

    selected_ids = {candidate["candidate_id"] for candidate in selected}
    for candidate in source_candidates:
        if candidate["candidate_id"] not in selected_ids and candidate["legal"]:
            candidate["legal"] = False
            candidate["rejection_reason"] = "source_budget_exhausted"

    return selected
```

- [ ] **Step 2: Replace single-best selection in `decide_with_trace(...)`**

Replace this Task 5 selection shape:

```python
legal_candidates = [candidate for candidate in source_candidates if candidate["legal"]]
best = max(legal_candidates, key=lambda candidate: candidate["score"], default=None)
for candidate in source_candidates:
    if best is not None and candidate["candidate_id"] == best["candidate_id"]:
        moves.append(candidate["move"])
        decision["chosen_candidate_ids"].append(candidate["candidate_id"])
    elif candidate["legal"]:
        candidate["rejection_reason"] = "not_highest_scoring_target_for_source"
    decision["candidates"].append(candidate)
```

With:

```python
selected = _select_budgeted_candidates(source_candidates)
selected_ids = {candidate["candidate_id"] for candidate in selected}
for candidate in source_candidates:
    if candidate["candidate_id"] in selected_ids:
        moves.append(candidate["move"])
        decision["chosen_candidate_ids"].append(candidate["candidate_id"])
    decision["candidates"].append(candidate)
```

- [ ] **Step 3: Update chosen reason**

When at least one move is selected, use:

```python
decision["chosen_reason"] = "selected budgeted production-scored legal targets"
```

- [ ] **Step 4: Add a direct unit test for `_select_budgeted_candidates(...)`**

Use plain candidate dictionaries so the budget algorithm can be tested without depending on geometry or observation parsing.

```python
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
```

```python
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
```

- [ ] **Step 5: Add a direct unit test for non-positive scores**

```python
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
```

- [ ] **Step 6: Run the selector tests and confirm they fail first**

```bash
python -m pytest \
  tests/test_main_decisions.py::test_select_budgeted_candidates_accepts_multiple_until_budget_exhausted \
  tests/test_main_decisions.py::test_select_budgeted_candidates_rejects_non_positive_scores \
  -q
```

Expected before implementation: fail because `_select_budgeted_candidates` does not exist.

- [ ] **Step 7: Implement `_select_budgeted_candidates(...)` and selection replacement**

After implementation, rerun:

```bash
python -m pytest \
  tests/test_main_decisions.py::test_select_budgeted_candidates_accepts_multiple_until_budget_exhausted \
  tests/test_main_decisions.py::test_select_budgeted_candidates_rejects_non_positive_scores \
  -q
```

Expected after implementation: pass.

### Task 7.4: Add Observation-Level Budgeting Tests

- [ ] **Step 1: Add a test proving one source can make multiple profitable moves if budget allows**

This test is the main behavior change from the current one-move-per-source logic.

```python
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
```

- [ ] **Step 2: Add a test proving the source never overcommits**

```python
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
```

Here `7` is the source budget after the early-game reserve of `max(3, production) == 3`.

- [ ] **Step 3: Add a test proving a valuable midgame source keeps reserve**

```python
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
```

Here `4` is `source.ships - desired_reserve == 12 - 8`.

- [ ] **Step 4: Add a test proving previous sun and insufficient-ship rejections still win priority**

```python
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
```

- [ ] **Step 5: Run all new observation tests and confirm they fail first**

```bash
python -m pytest \
  tests/test_main_decisions.py::test_agent_can_choose_multiple_budgeted_moves_from_one_source \
  tests/test_main_decisions.py::test_agent_caps_multiple_profitable_moves_by_source_budget \
  tests/test_main_decisions.py::test_valuable_midgame_source_keeps_reserve \
  tests/test_main_decisions.py::test_budgeting_preserves_sun_blocked_and_insufficient_ship_reasons \
  -q
```

Expected before implementation: at least the multiple-move test fails because current code chooses only one move per source.

- [ ] **Step 6: Implement the minimal code until the observation tests pass**

Do not add defense, orbit prediction, global multi-source allocation, or opponent modeling in this task. Keep scope limited to per-source budgeting.

Run:

```bash
python -m pytest \
  tests/test_main_decisions.py::test_agent_can_choose_multiple_budgeted_moves_from_one_source \
  tests/test_main_decisions.py::test_agent_caps_multiple_profitable_moves_by_source_budget \
  tests/test_main_decisions.py::test_valuable_midgame_source_keeps_reserve \
  tests/test_main_decisions.py::test_budgeting_preserves_sun_blocked_and_insufficient_ship_reasons \
  -q
```

Expected after implementation: pass.

### Task 7.5: Update Existing Tests For The New Selection Reason

- [ ] **Step 1: Update tests that assert the previous chosen reason**

Any test expecting:

```python
"selected highest-scoring legal production target per owned planet"
```

should now expect:

```python
"selected budgeted production-scored legal targets"
```

Files likely affected:
- `tests/test_main_decisions.py`
- `tests/test_generate_rollouts.py`

- [ ] **Step 2: Keep raw action tests focused on action shape**

If `test_agent_returns_raw_moves_for_existing_strategy` starts returning more than one move because `make_obs()` has multiple positive-score legal targets, either:
- adjust `make_obs()` so only the expected target is profitable, or
- change the assertion to prove all returned items are raw move lists:

```python
def test_agent_returns_raw_moves_for_existing_strategy():
    moves = main.agent(make_obs())

    assert moves
    assert all(isinstance(move, list) for move in moves)
    assert all(len(move) == 3 for move in moves)
```

Prefer the smallest edit that keeps the test about the wrapper contract instead of locking in a strategy detail.

- [ ] **Step 3: Run the existing decision and rollout tests**

```bash
python -m pytest tests/test_main_decisions.py tests/test_generate_rollouts.py -q
```

Expected: all tests pass.

### Task 7.6: Benchmark And Inspect Budgeting

- [ ] **Step 1: Run focused tests**

```bash
python -m pytest tests/test_main_decisions.py tests/test_geometry.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run the 50-game budgeting benchmark**

Use Python 3.11 if the current Python 3.13 environment cannot import `kaggle_environments`.

```bash
python3.11 evaluate.py --start-seed 1 --games 50 --opponents random --summary results/quick_budgeting.json
```

Expected command output shape:

```text
Agent version: nearest_sniper_v2_traceable
Games: 50
Wins: <integer>/50
Win rate: <decimal>
Errors: 0
Summary: results/quick_budgeting.json
```

- [ ] **Step 3: Inspect summary metrics**

Open `results/quick_budgeting.json` and check:

- `error_count` is `0`
- `games` is `50`
- `start_seed` is `1`
- `opponents` is `["random"]`
- `average_final_ship_score` is not a large regression from `results/quick_sun_safe.json`
- `win_rate` is not a large regression from `results/quick_sun_safe.json`

Promotion criterion:
- Prefer keeping Task 7 if it improves or roughly preserves the Task 6 benchmark.
- If win rate drops by more than 0.10 or average final ship score drops by more than 10 percent, keep the tests but tune reserve thresholds before promoting.

- [ ] **Step 4: Inspect rollout traces for overcommit**

Use a small script to prove no selected source overspends in the generated rollout traces:

```bash
python - <<'PY'
import json
from collections import defaultdict
from pathlib import Path

violations = []
for path in Path("data/rollouts_v2/nearest_sniper_v2_traceable").glob("*.jsonl"):
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        record = json.loads(line)
        if record.get("type") != "step":
            continue
        for decision in record.get("agent_decisions", []):
            moves_by_source = defaultdict(int)
            source_ships = {}
            for candidate in decision.get("candidates", []):
                source_id = candidate["source_planet_id"]
                source_ships[source_id] = candidate["score_components"]["source_ships"]
            for move in decision.get("chosen_moves", []):
                moves_by_source[move[0]] += move[2]
            for source_id, ships_sent in moves_by_source.items():
                if ships_sent > source_ships.get(source_id, 0):
                    violations.append((str(path), line_number, source_id, ships_sent, source_ships.get(source_id)))

if violations:
    print("overcommit violations:")
    for violation in violations[:20]:
        print(violation)
    raise SystemExit(1)

print("No overcommit violations found")
PY
```

Expected:

```text
No overcommit violations found
```

- [ ] **Step 5: Run the full test suite**

```bash
python -m pytest -q
```

Expected: all tests pass.

### Task 7.7: Commit

- [ ] **Step 1: Review changed files**

```bash
git status --short
git diff -- main.py tests/test_main_decisions.py tests/test_generate_rollouts.py nextsteps.md
```

Expected:
- `main.py` contains phase-aware reserves and `_select_budgeted_candidates(...)`.
- `tests/test_main_decisions.py` contains helper, selector, and observation-level budget tests.
- `tests/test_generate_rollouts.py` only changes expected trace wording/score fields if needed.
- `results/quick_budgeting.json` exists.

- [ ] **Step 2: Commit source, tests, and benchmark evidence**

```bash
git add main.py tests/test_main_decisions.py tests/test_generate_rollouts.py results/quick_budgeting.json
git commit -m "add source ship budgeting"
```

If this detailed Task 7 plan update is part of the same change, include it:

```bash
git add nextsteps.md
git commit -m "detail source ship budgeting plan"
```

---

## Task 8: Add Orbit-Aware Targeting

**Status:** Implemented with `prediction.py` and `tests/test_prediction.py`.

Actual helper API:

- `planet_by_id(planets)`
- `is_orbiting_planet(planet, center=(50.0, 50.0), rotation_radius_limit=50.0)`
- `predict_orbit_position(initial_planet, angular_velocity, turns, center=(50.0, 50.0))`
- `sample_orbit_intercept(source, target, initial_target, angular_velocity, ships, max_turns=80, timing_tolerance=2.0)`

`main.py` uses `initial_planets` and `angular_velocity` when `initial_planets` is present. If `initial_planets` is absent, static direct-shot behavior is preserved for synthetic tests and simple observations.

Actual orbit trace fields in `score_components`:

- `target_is_orbiting`
- `intercept_turn`
- `timing_error`
- `predicted_target_x`
- `predicted_target_y`
- `used_initial_planet`

Actual orbit rejection reasons:

- `no_orbit_intercept`
- `orbit_intercept_sun_blocked`

**Files:**
- Create: `prediction.py`
- Test: `tests/test_prediction.py`
- Modify: `main.py`

- [ ] **Step 1: Predict orbiting planet positions**

Use `initial_planets` and `angular_velocity` when available. A planet is orbiting when its center distance from `(50, 50)` plus radius is less than `50`.

- [ ] **Step 2: Add approximate intercept sampling**

For orbiting targets:

- sample future turns within a practical range
- predict target position at each turn
- compute travel turns to that position
- choose the sample with lowest timing error
- reject if timing error is too high or the shot hits the sun

- [ ] **Step 3: Add tests**

Cover:

- orbit prediction keeps radius constant around the sun
- zero future turns returns the initial position
- positive angular velocity rotates in the expected direction
- intercept sampling returns a deterministic angle for a simple case

- [ ] **Step 4: Benchmark**

```bash
pytest tests/test_prediction.py tests/test_main_decisions.py tests/test_geometry.py -q
python evaluate.py --start-seed 1 --games 50 --opponents random --summary results/quick_orbit_aware.json
```

- [ ] **Step 5: Commit**

```bash
git add prediction.py tests/test_prediction.py main.py tests/test_main_decisions.py results/quick_orbit_aware.json
git commit -m "add orbit-aware targeting"
```

---

## Task 9: Add Basic Defense

**Files:**
- Modify: `main.py`
- Test: `tests/test_main_decisions.py`

- [ ] **Step 1: Detect incoming enemy fleets**

For each enemy fleet, project likely arrival against owned planets using current heading, distance to planet, and sun/planet path checks.

- [ ] **Step 2: Generate reinforcement candidates**

Create `reinforce` candidates when an owned planet is likely to be captured and another owned planet can send enough ships in time.

- [ ] **Step 3: Prioritize valuable defenses**

Score defense by:

- target production
- ships saved
- arrival timing
- cost to reinforce
- whether the planet is doomed even after reinforcement

- [ ] **Step 4: Add tests**

Cover:

- high-production threatened planet gets reinforced
- doomed low-value planet is not over-defended
- reinforcement does not drain the only safe high-value planet

- [ ] **Step 5: Benchmark**

```bash
pytest tests/test_main_decisions.py tests/test_geometry.py -q
python evaluate.py --start-seed 1 --games 100 --opponents random --summary results/standard_defense.json
```

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main_decisions.py results/standard_defense.json
git commit -m "add basic defensive reinforcements"
```

---

## Task 10: Add Opportunistic Attacks

**Files:**
- Modify: `main.py`
- Test: `tests/test_main_decisions.py`

- [ ] **Step 1: Score enemy planets separately from neutrals**

Prefer enemy planets that have high production, low current garrison, poor reinforcement prospects, or just launched ships.

- [ ] **Step 2: Add attack safety margins**

Estimate target production before arrival and add a small margin. Reject attacks that expose a better owned planet unless the target is decisive.

- [ ] **Step 3: Add tests**

Cover:

- weakened enemy planet is attacked over a lower-value neutral
- attack ships include expected production before arrival
- high-risk overextension is rejected

- [ ] **Step 4: Benchmark**

```bash
pytest tests/test_main_decisions.py -q
python evaluate.py --start-seed 1 --games 100 --opponents random --summary results/standard_attacks.json
```

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main_decisions.py results/standard_attacks.json
git commit -m "add opportunistic attack scoring"
```

---

## Task 11: Add Endgame Logic

**Files:**
- Modify: `main.py`
- Test: `tests/test_main_decisions.py`

- [ ] **Step 1: Detect final phase**

Use `step >= 470` as the first endgame threshold.

- [ ] **Step 2: Convert surplus ships into useful pressure**

Prefer attacks that can arrive before turn 500. If an attack cannot arrive, launch only when it preserves score without enabling a late planet flip.

- [ ] **Step 3: Add tests**

Cover:

- before turn 470 normal scoring applies
- after turn 470 surplus ships prefer reachable targets
- agent does not empty a planet that can be captured immediately

- [ ] **Step 4: Benchmark long games**

```bash
pytest tests/test_main_decisions.py -q
python evaluate.py --start-seed 1 --games 100 --opponents random --summary results/standard_endgame.json
```

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main_decisions.py results/standard_endgame.json
git commit -m "add endgame score conversion"
```

---

## Task 12: Run Submission-Grade Validation

**Files:**
- Read: `results/*.json`
- Modify only if needed: `main.py`, tests

- [ ] **Step 1: Run full tests**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run held-out local evaluation**

Use seeds not used for quick tuning:

```bash
python evaluate.py --start-seed 1001 --games 200 --opponents random --summary results/submission_candidate.json
```

Expected:

- zero runtime errors
- zero invalid actions
- better performance than the original nearest baseline on the same seed range
- runtime comfortably below Kaggle limits

- [ ] **Step 3: Inspect representative traces**

Open a few rollout JSONL files from wins and losses. Check for:

- missed easy expansion
- sun crashes or sun-blocked rejected candidates
- obvious overcommit
- failed defense
- late-game emptying of important planets

- [ ] **Step 4: Freeze candidate version**

Update `AGENT_VERSION` in `main.py` to a descriptive version such as:

```python
AGENT_VERSION = "rule_based_submission_v1"
```

Run:

```bash
pytest -q
python evaluate.py --start-seed 1001 --games 200 --opponents random --summary results/submission_rule_based_submission_v1.json
```

- [ ] **Step 5: Commit**

```bash
git add main.py tests results/submission_rule_based_submission_v1.json
git commit -m "prepare rule based submission candidate"
```

---

## Task 13: Package The Submission

**Files:**
- Runtime files: `main.py` and any helper modules imported by `main.py`
- Output: `submission.tar.gz` only if multi-file

- [ ] **Step 1: Choose packaging mode**

Use single-file submission if `main.py` has no helper imports besides standard library and Kaggle environment imports:

```bash
kaggle competitions submit orbit-wars -f main.py -m "rule_based_submission_v1"
```

Use tarball submission if `main.py` imports helper modules such as `geometry.py` or `prediction.py`:

```bash
tar -czf submission.tar.gz main.py geometry.py prediction.py
kaggle competitions submit orbit-wars -f submission.tar.gz -m "rule_based_submission_v1"
```

- [ ] **Step 2: Validate package contents**

For tarball mode:

```bash
tar -tzf submission.tar.gz
```

Expected: only runtime files are present. No `data/`, `results/`, `replays/`, `.venv/`, tests, logs, credentials, or local-only scripts.

- [ ] **Step 3: Run final local smoke**

```bash
python -c "from kaggle_environments import make; env = make('orbit_wars', configuration={'seed': 42}, debug=True); env.run(['main.py', 'random']); print([(i, s.reward, s.status) for i, s in enumerate(env.steps[-1])])"
```

Expected: no exception and valid final statuses.

---

## Task 14: Submit And Monitor Kaggle

**Files:**
- Create/download as generated artifacts: `replays/`, `logs/`
- Read: Kaggle CLI outputs

- [ ] **Step 1: Verify Kaggle access**

```bash
kaggle competitions list -s "orbit wars"
kaggle competitions list --group entered
```

If the competition is not listed under entered competitions, join it in the browser first:

```text
https://www.kaggle.com/competitions/orbit-wars
```

- [ ] **Step 2: Submit**

Single-file:

```bash
kaggle competitions submit orbit-wars -f main.py -m "rule_based_submission_v1"
```

Tarball:

```bash
kaggle competitions submit orbit-wars -f submission.tar.gz -m "rule_based_submission_v1"
```

- [ ] **Step 3: Check submission status**

```bash
kaggle competitions submissions orbit-wars
```

Record the submission ID.

- [ ] **Step 4: Download episodes, replays, and logs**

```bash
SUBMISSION_ID=12345678
EPISODE_ID=123456789
kaggle competitions episodes "$SUBMISSION_ID"
kaggle competitions episodes "$SUBMISSION_ID" -v
kaggle competitions replay "$EPISODE_ID" -p ./replays
kaggle competitions logs "$EPISODE_ID" 0 -p ./logs
```

- [ ] **Step 5: Check leaderboard**

```bash
kaggle competitions leaderboard orbit-wars -s
```

---

## Task 15: Replay Feedback Loop

**Files:**
- Generated: `replays/`, `logs/`
- Modify based on findings: `main.py`, helper modules, tests
- Optional future files: `dpo_data.py`, `dpo_ranker.py`, `dpo_judge.py`

- [ ] **Step 1: Classify each loss**

Use these tags:

- `missed_expansion`
- `sun_risk`
- `bad_orbit_intercept`
- `overcommit`
- `missed_defense`
- `weak_attack`
- `bad_endgame`
- `runtime_error`
- `invalid_action`

- [ ] **Step 2: Convert clear failures into tests**

For every clear replay failure, create a compact synthetic observation in tests that reproduces the decision pressure.

- [ ] **Step 3: Fix only one failure class at a time**

Run:

```bash
pytest -q
python evaluate.py --start-seed 1001 --games 200 --opponents random --summary results/submission_candidate_after_replay_fix.json
```

Promote only if the fix improves the replay class without broad regression.

- [ ] **Step 4: Resubmit improved versions**

Use descriptive messages:

```bash
kaggle competitions submit orbit-wars -f submission.tar.gz -m "rule_based_submission_v2_defense_fix"
```

- [ ] **Step 5: Defer DPO until the rule engine plateaus**

Start DPO only after:

- rollout tracing is reliable
- evaluation can compare old/new versions on fixed seeds
- candidate traces include enough scoring detail
- Kaggle replay failures show ranking mistakes rather than missing rule logic

The final Kaggle runtime must not require `dpo_judge.py`, API keys, or network calls.

---

## Final Pre-Submission Checklist

- [ ] `main.py` exposes `agent(obs)`.
- [ ] All runtime imports are packaged.
- [ ] `pytest -q` passes.
- [ ] Held-out evaluation summary exists under `results/`.
- [ ] Rollout trace validation has no false `action_mismatch` errors.
- [ ] Generated data, logs, and replays may be tracked in git, but are not bundled into the runtime submission package.
- [ ] No secrets, virtualenv files, tests, or local-only analysis scripts are bundled.
- [ ] No API keys, network calls, debug spam, browser calls, or local file writes exist in the Kaggle runtime path.
- [ ] Agent runtime is comfortably below the turn limit.
- [ ] Kaggle rules have been accepted.
- [ ] Submission status, episode IDs, replay paths, and leaderboard result are recorded after upload.
