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
- `results/local_rollouts_v2_smoke.json` shows many `action_mismatch` errors, so trace validation is not yet trustworthy.
- `plan.md` defines the long-term direction: strong rule-based agent first, optional DPO candidate ranking later.
- `.gitignore` currently ignores `.venv`, `__pycache__`, and `*.py[cod]`, but generated data/results are not ignored.

## Submission Policy

- Submit only code needed by the runtime agent.
- Do not submit API keys, judge scripts, large rollout data, replay logs, or exploratory notebooks.
- Do not depend on network calls, Kaggle CLI, local files, or environment secrets from `main.py`.
- Promote a new agent version only when it beats the previous version on fixed held-out seeds or fixes a verified replay failure without a broader regression.
- Prefer simple deterministic rule logic until the evaluation harness is reliable.

---

## Task 1: Fix Rollout Trace Validation

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

Expected: tests pass, but the generated summary currently contains `action_mismatch` entries for `main.py`.

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

## Task 2: Protect Generated Artifacts

**Files:**
- Modify: `.gitignore`
- Keep small benchmark summaries under: `results/` when they are useful for comparing agent versions.

- [ ] **Step 1: Decide what stays in git**

Keep source files, tests, docs, and small benchmark summaries. Treat large rollout JSONL, replays, logs, and local competition downloads as generated artifacts.

- [ ] **Step 2: Update `.gitignore`**

Add:

```gitignore
data/
replays/
logs/
orbit-wars-data/
submission.tar.gz
```

If small result summaries should remain tracked, do not ignore all of `results/`. Instead, avoid committing bulky result files manually.

- [ ] **Step 3: Check current tracked/generated files**

Run:

```bash
git status --short
git ls-files data results replays logs orbit-wars-data 2>/dev/null
```

Expected: no accidental large generated files are staged for submission work.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "ignore generated rollout artifacts"
```

---

## Task 3: Build A Real Evaluation Command

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
- fleet speed increases with ship count
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

**Files:**
- Modify: `main.py`
- Test: `tests/test_main_decisions.py`

- [ ] **Step 1: Track per-source available ships**

When multiple candidates originate from the same planet, choose moves in descending score order and subtract ships from that source budget after each accepted move.

- [ ] **Step 2: Keep reserves**

Use phase-aware minimum reserves:

- early game: keep at least 3 ships or one turn of production
- midgame: keep at least 5 ships on valuable planets
- late game: keep enough ships to avoid easy flips unless launching improves final score

- [ ] **Step 3: Add tests**

Cover:

- no source sends more ships than it has
- multiple profitable moves from one source are capped by budget
- a high-value home planet keeps a reserve

- [ ] **Step 4: Benchmark**

```bash
pytest tests/test_main_decisions.py -q
python evaluate.py --start-seed 1 --games 50 --opponents random --summary results/quick_budgeting.json
```

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_main_decisions.py results/quick_budgeting.json
git commit -m "add source ship budgeting"
```

---

## Task 8: Add Orbit-Aware Targeting

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
- [ ] No generated data, logs, replays, secrets, or virtualenv files are bundled.
- [ ] No API keys, network calls, debug spam, browser calls, or local file writes exist in the Kaggle runtime path.
- [ ] Agent runtime is comfortably below the turn limit.
- [ ] Kaggle rules have been accepted.
- [ ] Submission status, episode IDs, replay paths, and leaderboard result are recorded after upload.
