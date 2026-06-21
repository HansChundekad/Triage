# Phase 7B — Phoenix Evaluator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score each repro attempt with two LLM-as-judge evaluators (did it genuinely reproduce the *reported* bug; is the root-cause hypothesis correct) plus a deterministic honesty check, and log the scores **onto the `repro_attempt` spans** in Phoenix so the fail→succeed improvement is visible alongside the traces.

**Architecture:** A `ground_truth.py` fixture holds the planted-bug expectations (single source of truth, never shown to the agents). `judges.py` builds two `phoenix.evals.create_classifier` judges; `code_checks.py` is a pure honesty function. `run_eval.py` reads the run's attempts from `RunArtifacts` (and/or pulls `repro_attempt` spans from Phoenix), runs the judges + check per attempt, then logs results to the matching spans via the modern `phoenix.client` annotations API. Wired to run **inline** at the end of `scripts/phase7_traced_run.py`.

**Tech Stack:** `arize-phoenix-evals` (3.x: `create_classifier`, `LLM`, `evaluate_dataframe`), `arize-phoenix-client` (`Client().spans.log_span_annotations_dataframe`), `pandas`, `anthropic`, `pytest`.

## Global Constraints

- **Depends on Phase 7A** (`triage/tracing/artifacts.py::RunArtifacts`, the `repro_attempt`
  span name + its `attempt.number` / `bug.detected` / `browserbase.session_url` attributes,
  and `scripts/phase7_traced_run.py`). Do not start until 7A Tasks 3, 5, 7 are merged.
- Use the repo venv `.venv/`. Install/test: `.venv/bin/pip install -e ".[dev]"` · `.venv/bin/pytest`.
- TDD — failing test first. Per-task commits. Never modify `triage/shared/band.py`.
- Judge model: `claude-sonnet-4-6`. Evaluator outcomes scored per **attempt**, not per run.
- Phoenix project name: `triage-bug-repro` (matches 7A).
- **Verify against the installed package before relying on it** (drift flags from the design
  spec §2): confirm `create_classifier` / `evaluate_dataframe` signatures, the result columns
  (`label` / `score` / `explanation`), whether `phoenix.evals` ships an Anthropic `LLM`
  adapter (else use LiteLLM → `anthropic/claude-sonnet-4-6`), and the exact
  `log_span_annotations_dataframe` parameters. **Flag the adapter choice in the commit body.**

---

### Task 0: Verify the evals + client API against the installed packages

**Files:** none (investigation; record findings in the Task 1 commit body).

- [ ] **Step 1: Install the eval + client packages and introspect**

```bash
.venv/bin/pip install arize-phoenix-evals arize-phoenix-client pandas
.venv/bin/python - <<'PY'
import inspect
from phoenix.evals import create_classifier, evaluate_dataframe
from phoenix.evals.llm import LLM
print("create_classifier:", inspect.signature(create_classifier))
print("evaluate_dataframe:", inspect.signature(evaluate_dataframe))
print("LLM:", inspect.signature(LLM))
try:
    from phoenix.client import Client
    print("client.spans:", [m for m in dir(Client().spans) if "annot" in m or "eval" in m])
except Exception as e:
    print("client introspect note:", e)
PY
```

Expected: prints real signatures. **Record them.** Confirm whether `LLM(provider="anthropic", ...)`
is accepted; if it raises, the judges in Task 2 use `LLM(provider="litellm", model="anthropic/claude-sonnet-4-6")`.
If `evaluate_dataframe` returns columns other than `label`/`score`/`explanation`, adjust Task 3's
column mapping. **If any import fails, stop and flag — do not invent the API.**

- [ ] **Step 2: Add the deps to pyproject**

Append to `pyproject.toml` `dependencies`: `arize-phoenix-evals`, `arize-phoenix-client`,
`pandas` (pin to the resolved versions from Step 1).

```bash
git add pyproject.toml
git commit -m "chore(phase7b): add arize-phoenix-evals + client + pandas; record verified API"
```

---

### Task 1: `ground_truth.py` — the planted-bug fixture

**Files:**
- Create: `triage/eval/__init__.py`
- Create: `triage/eval/ground_truth.py`
- Test: `tests/test_eval_ground_truth.py`

**Interfaces:**
- Produces: `PLANTED_BUG: PlantedBug` dataclass with fields:
  `symptom: str`, `console_fingerprint: str`, `root_cause: str`. Values describe the known bug
  (blank screen on deleting the last task; `Cannot read properties of undefined`; reads an
  element/length of the items array after it's emptied by the final delete). Mirrors the
  detection constant `browser.CRASH_SUBSTRING` for `console_fingerprint`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eval_ground_truth.py
from triage.eval.ground_truth import PLANTED_BUG
from triage.repro_agent.browser import CRASH_SUBSTRING


def test_ground_truth_matches_detection_fingerprint():
    assert PLANTED_BUG.console_fingerprint == CRASH_SUBSTRING
    assert "blank" in PLANTED_BUG.symptom.lower()
    assert PLANTED_BUG.root_cause  # non-empty mechanistic statement
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_eval_ground_truth.py -v`
Expected: FAIL — `ModuleNotFoundError: triage.eval.ground_truth`.

- [ ] **Step 3: Write minimal implementation**

```python
# triage/eval/__init__.py
"""Phoenix evaluator (Phase 7B): LLM judges + code honesty check, per attempt."""
```

```python
# triage/eval/ground_truth.py
"""Planted-bug ground truth — single source of truth for the root-cause judge.

Deliberately NOT shown to the agents; only the evaluator sees it.
"""
from __future__ import annotations

from dataclasses import dataclass

from triage.repro_agent.browser import CRASH_SUBSTRING


@dataclass(frozen=True)
class PlantedBug:
    symptom: str
    console_fingerprint: str
    root_cause: str


PLANTED_BUG = PlantedBug(
    symptom=(
        "Deleting the last remaining task makes the app render a blank screen "
        "instead of an empty-list state."
    ),
    console_fingerprint=CRASH_SUBSTRING,
    root_cause=(
        "After the final delete empties the tasks array, the render path still "
        "dereferences an element/length of that now-empty array (e.g. items[0] / "
        "items.length on undefined), throwing a TypeError that blanks the page."
    ),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_eval_ground_truth.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add triage/eval/__init__.py triage/eval/ground_truth.py tests/test_eval_ground_truth.py
git commit -m "feat(phase7b): ground_truth.py planted-bug fixture for the root-cause judge"
```

---

### Task 2: `judges.py` — two LLM-as-judge classifiers + input builders

**Files:**
- Create: `triage/eval/judges.py`
- Test: `tests/test_eval_judges.py`

**Interfaces:**
- Consumes: `PLANTED_BUG` (Task 1); `phoenix.evals.create_classifier` / `LLM` (Task 0 API).
- Produces:
  - `build_fidelity_input(issue_text: str, attempt: dict) -> dict` — maps an attempt record
    (from `RunArtifacts.load_attempts()`: `evidence`, `console_errors`, `bug_detected`) +
    the issue text into the `{input, output}` keys the fidelity judge template reads.
  - `build_root_cause_input(issue_text: str, hypothesis_root_cause: str) -> dict` — maps the
    issue + `PLANTED_BUG.root_cause` (ground truth) + the agent's hypothesis into the
    root-cause judge keys.
  - `make_fidelity_judge(llm)` / `make_root_cause_judge(llm)` — return `create_classifier`
    evaluators. Choices: fidelity `{"reproduced":1.0,"inconclusive":0.5,"not_reproduced":0.0}`;
    root cause `{"correct":1.0,"partially_correct":0.5,"incorrect":0.0}`.
  - `build_judge_llm(cfg)` — returns an `LLM` (Anthropic adapter, or LiteLLM→Anthropic per
    Task 0). Isolated so tests don't need it.

> The input-builders are the unit-tested logic (pure, deterministic). The `create_classifier`
> objects wrap live LLM calls, exercised only in the optional live smoke — tests assert the
> builder output shape and the choice maps, not live judgments.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eval_judges.py
from triage.eval.judges import (
    build_fidelity_input, build_root_cause_input,
    FIDELITY_CHOICES, ROOT_CAUSE_CHOICES,
)
from triage.eval.ground_truth import PLANTED_BUG


def test_fidelity_input_carries_issue_and_evidence():
    attempt = {"bug_detected": True, "evidence": ["blank body"],
               "console_errors": ["Cannot read properties of undefined"]}
    out = build_fidelity_input("app goes blank when I delete my last task", attempt)
    assert "delete my last task" in out["input"]
    assert "Cannot read properties of undefined" in out["output"]
    assert "BUG REPRODUCED" in out["output"] or "True" in out["output"]


def test_root_cause_input_includes_ground_truth_and_hypothesis():
    out = build_root_cause_input("app goes blank...", "reads items[0] after delete")
    assert PLANTED_BUG.root_cause in out["reference"]
    assert "reads items[0] after delete" in out["output"]


def test_choice_maps_are_scored():
    assert FIDELITY_CHOICES["reproduced"] == 1.0
    assert FIDELITY_CHOICES["not_reproduced"] == 0.0
    assert ROOT_CAUSE_CHOICES["correct"] == 1.0
    assert ROOT_CAUSE_CHOICES["incorrect"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_eval_judges.py -v`
Expected: FAIL — `ModuleNotFoundError: triage.eval.judges`.

- [ ] **Step 3: Write minimal implementation**

```python
# triage/eval/judges.py
"""LLM-as-judge classifiers + pure input builders for repro-attempt scoring.

create_classifier / LLM signatures verified against the installed arize-phoenix-evals
in Task 0 — adjust prompt_template kwarg name / choices kwarg if drift was recorded.
"""
from __future__ import annotations

from triage.eval.ground_truth import PLANTED_BUG

FIDELITY_CHOICES = {"reproduced": 1.0, "inconclusive": 0.5, "not_reproduced": 0.0}
ROOT_CAUSE_CHOICES = {"correct": 1.0, "partially_correct": 0.5, "incorrect": 0.0}

_FIDELITY_TEMPLATE = (
    "You are grading whether a browser-automation attempt genuinely reproduced "
    "the REPORTED bug (not merely produced some error).\n\n"
    "Reported issue:\n{input}\n\n"
    "Attempt evidence:\n{output}\n\n"
    "Answer 'reproduced' only if the observed behavior matches the reported bug; "
    "'not_reproduced' if it clearly did not; 'inconclusive' if the evidence is "
    "insufficient."
)
_ROOT_CAUSE_TEMPLATE = (
    "You are grading whether a diagnosed root cause is correct.\n\n"
    "Reported issue:\n{input}\n\n"
    "Known correct root cause (ground truth):\n{reference}\n\n"
    "Proposed root cause:\n{output}\n\n"
    "Answer 'correct', 'partially_correct', or 'incorrect'."
)


def build_fidelity_input(issue_text: str, attempt: dict) -> dict:
    verdict = "BUG REPRODUCED" if attempt.get("bug_detected") else "BUG NOT REPRODUCED"
    evidence = "\n".join(attempt.get("evidence", []))
    console = "\n".join(attempt.get("console_errors", []))
    return {
        "input": issue_text,
        "output": f"verdict: {verdict}\nconsole:\n{console}\nevidence:\n{evidence}",
    }


def build_root_cause_input(issue_text: str, hypothesis_root_cause: str) -> dict:
    return {
        "input": issue_text,
        "reference": PLANTED_BUG.root_cause,
        "output": hypothesis_root_cause,
    }


def make_fidelity_judge(llm):
    from phoenix.evals import create_classifier
    return create_classifier(
        name="repro_fidelity", llm=llm,
        prompt_template=_FIDELITY_TEMPLATE, choices=FIDELITY_CHOICES,
    )


def make_root_cause_judge(llm):
    from phoenix.evals import create_classifier
    return create_classifier(
        name="root_cause_correctness", llm=llm,
        prompt_template=_ROOT_CAUSE_TEMPLATE, choices=ROOT_CAUSE_CHOICES,
    )


def build_judge_llm(cfg):
    """Anthropic judge LLM (or LiteLLM->Anthropic if no native adapter — see Task 0)."""
    from phoenix.evals.llm import LLM
    try:
        return LLM(provider="anthropic", model="claude-sonnet-4-6")
    except Exception:  # noqa: BLE001 — adapter not present; fall back to LiteLLM
        return LLM(provider="litellm", model="anthropic/claude-sonnet-4-6")
```

> If Task 0 recorded a different `create_classifier` kwarg (e.g. `template=` not
> `prompt_template=`, or `rails=`/`choices=` shape), apply it here verbatim.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_eval_judges.py -v`
Expected: PASS (the three pure tests; live judge objects not constructed in CI).

- [ ] **Step 5: Commit**

```bash
git add triage/eval/judges.py tests/test_eval_judges.py
git commit -m "feat(phase7b): repro-fidelity + root-cause LLM judges and input builders"
```

---

### Task 3: `code_checks.py` — deterministic honesty eval

**Files:**
- Create: `triage/eval/code_checks.py`
- Test: `tests/test_eval_code_checks.py`

**Interfaces:**
- Consumes: nothing (pure). Mirrors `browser.detect_bug` semantics.
- Produces: `honesty_check(bug_detected: bool, blank_body: bool, console_match: bool) ->
  HonestyResult` with `score: float` (1.0 honest, 0.0 dishonest), `label: str`
  ("honest"/"inconsistent"), `explanation: str`. Honest iff
  `bug_detected == (blank_body and console_match)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_eval_code_checks.py
from triage.eval.code_checks import honesty_check


def test_honest_when_detection_matches_signals():
    r = honesty_check(bug_detected=True, blank_body=True, console_match=True)
    assert r.score == 1.0 and r.label == "honest"


def test_inconsistent_when_claimed_without_both_signals():
    r = honesty_check(bug_detected=True, blank_body=True, console_match=False)
    assert r.score == 0.0 and r.label == "inconsistent"


def test_honest_negative():
    r = honesty_check(bug_detected=False, blank_body=False, console_match=True)
    assert r.score == 1.0 and r.label == "honest"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_eval_code_checks.py -v`
Expected: FAIL — `ModuleNotFoundError: triage.eval.code_checks`.

- [ ] **Step 3: Write minimal implementation**

```python
# triage/eval/code_checks.py
"""Deterministic honesty eval — bug.detected must equal the dual-signal AND."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HonestyResult:
    score: float
    label: str
    explanation: str


def honesty_check(bug_detected: bool, blank_body: bool, console_match: bool) -> HonestyResult:
    expected = blank_body and console_match
    honest = bug_detected == expected
    return HonestyResult(
        score=1.0 if honest else 0.0,
        label="honest" if honest else "inconsistent",
        explanation=(
            f"bug_detected={bug_detected}; blank_body={blank_body}; "
            f"console_match={console_match}; expected={expected}"
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_eval_code_checks.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add triage/eval/code_checks.py tests/test_eval_code_checks.py
git commit -m "feat(phase7b): deterministic honesty eval (defends rule #8)"
```

---

### Task 4: `run_eval.py` — score per attempt + log to spans, wired inline

**Files:**
- Create: `triage/eval/run_eval.py`
- Modify: `scripts/phase7_traced_run.py` (uncomment/activate the 7B hook)
- Create: `scripts/phase7_eval.py` (standalone re-score entrypoint)
- Test: `tests/test_eval_run_eval.py`

**Interfaces:**
- Consumes: `RunArtifacts.load_attempts()` (7A Task 3), `build_fidelity_input` /
  `build_root_cause_input` / `make_*_judge` / `build_judge_llm` (Task 2), `honesty_check`
  (Task 3), and the Phoenix `repro_attempt` spans (matched by `attempt.number`).
- Produces:
  - `build_eval_dataframe(attempts, issue_text, hypothesis_root_cause) -> pandas.DataFrame` —
    one row per attempt with the judge input columns + a `attempt_number` column. **Pure /
    unit-tested.**
  - `score_attempts(df, *, fidelity_judge, root_cause_judge) -> pandas.DataFrame` — runs
    `evaluate_dataframe` + merges in `honesty_check` rows. (Live; thin wrapper.)
  - `run_eval(cfg, repro_state, artifacts, *, span_lookup=None) -> pandas.DataFrame` —
    orchestrates: load attempts → build df → score → map each row to its `repro_attempt`
    `span_id` → `Client().spans.log_span_annotations_dataframe(...)`. Returns the scored df.
    `span_lookup` is injected in tests (maps `attempt_number -> span_id`); defaults to a
    Phoenix query by `attempt.number` within project `triage-bug-repro`.

> Only `build_eval_dataframe` is unit-tested (pure). `score_attempts` / `run_eval` are thin
> orchestration over live Phoenix + LLM calls, verified in the live smoke (Step 4). Keep the
> live surface tiny so the logic that can break lives in the pure builder.

- [ ] **Step 1: Write the failing test (pure builder only)**

```python
# tests/test_eval_run_eval.py
from triage.eval.run_eval import build_eval_dataframe


def test_build_eval_dataframe_one_row_per_attempt():
    attempts = [
        {"attempt": 1, "bug_detected": False, "evidence": ["empty"], "console_errors": []},
        {"attempt": 2, "bug_detected": True, "evidence": ["blank"],
         "console_errors": ["Cannot read properties of undefined"]},
    ]
    df = build_eval_dataframe(attempts, issue_text="app blanks on delete",
                              hypothesis_root_cause="reads items[0] after delete")
    assert list(df["attempt_number"]) == [1, 2]
    assert "app blanks on delete" in df.iloc[0]["input"]
    # fidelity output column reflects the per-attempt verdict
    assert "BUG NOT REPRODUCED" in df.iloc[0]["fidelity_output"]
    assert "BUG REPRODUCED" in df.iloc[1]["fidelity_output"]
    # root-cause columns carry ground truth + hypothesis
    assert "reads items[0] after delete" in df.iloc[0]["root_cause_output"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_eval_run_eval.py -v`
Expected: FAIL — `ModuleNotFoundError: triage.eval.run_eval`.

- [ ] **Step 3: Write minimal implementation**

```python
# triage/eval/run_eval.py
"""Per-attempt scoring + logging onto repro_attempt spans (modern phoenix.client)."""
from __future__ import annotations

import pandas as pd

from triage.eval.judges import (
    build_fidelity_input, build_root_cause_input,
    make_fidelity_judge, make_root_cause_judge, build_judge_llm,
)
from triage.eval.code_checks import honesty_check


def build_eval_dataframe(attempts, issue_text, hypothesis_root_cause) -> pd.DataFrame:
    rows = []
    for a in attempts:
        fid = build_fidelity_input(issue_text, a)
        rc = build_root_cause_input(issue_text, hypothesis_root_cause)
        rows.append({
            "attempt_number": a["attempt"],
            "input": issue_text,
            "fidelity_output": fid["output"],
            "root_cause_reference": rc["reference"],
            "root_cause_output": rc["output"],
            "bug_detected": a.get("bug_detected", False),
        })
    return pd.DataFrame(rows)


def score_attempts(df, *, fidelity_judge, root_cause_judge):
    from phoenix.evals import evaluate_dataframe
    # Map our columns into each judge's template keys, then evaluate.
    fid_df = df.rename(columns={"fidelity_output": "output"})[["input", "output"]]
    rc_df = df.rename(columns={"root_cause_output": "output",
                               "root_cause_reference": "reference"})[["input", "reference", "output"]]
    fid_scores = evaluate_dataframe(fid_df, [fidelity_judge])
    rc_scores = evaluate_dataframe(rc_df, [root_cause_judge])
    out = df.copy()
    out["repro_fidelity_label"] = fid_scores["label"].values
    out["repro_fidelity_score"] = fid_scores["score"].values
    out["root_cause_label"] = rc_scores["label"].values
    out["root_cause_score"] = rc_scores["score"].values
    return out


def run_eval(cfg, repro_state, artifacts, *, span_lookup=None, hypothesis_root_cause=""):
    attempts = artifacts.load_attempts()
    if not attempts:
        return pd.DataFrame()
    issue_text = cfg.github_issue_url  # the harness may pass full issue text instead
    df = build_eval_dataframe(attempts, issue_text, hypothesis_root_cause)

    llm = build_judge_llm(cfg)
    scored = score_attempts(df, fidelity_judge=make_fidelity_judge(llm),
                            root_cause_judge=make_root_cause_judge(llm))

    # honesty (code) eval per attempt — needs the per-attempt signal booleans; if the
    # attempt record lacks them, fall back to bug_detected==bug_detected (always honest).
    scored["honesty_score"] = [
        honesty_check(a.get("bug_detected", False),
                      a.get("blank_body", a.get("bug_detected", False)),
                      a.get("console_match", a.get("bug_detected", False))).score
        for a in attempts
    ]

    if span_lookup is None:
        span_lookup = _phoenix_span_lookup(cfg)
    _log_to_spans(scored, span_lookup)
    return scored


def _phoenix_span_lookup(cfg):
    """Return {attempt_number: span_id} by querying repro_attempt spans in Phoenix."""
    from phoenix.client import Client
    client = Client()
    spans = client.spans.get_spans_dataframe(
        project_identifier="triage-bug-repro",
        # filter to repro_attempt spans; adjust to the verified query API (Task 0).
    )
    lookup = {}
    for _, row in spans.iterrows():
        if row.get("name") == "repro_attempt":
            lookup[int(row["attributes.attempt.number"])] = row["context.span_id"]
    return lookup


def _log_to_spans(scored, span_lookup):
    from phoenix.client import Client
    client = Client()
    records = []
    for _, r in scored.iterrows():
        span_id = span_lookup.get(int(r["attempt_number"]))
        if not span_id:
            continue
        records.append({"span_id": span_id, "label": r["repro_fidelity_label"],
                        "score": float(r["repro_fidelity_score"])})
    if records:
        client.spans.log_span_annotations_dataframe(
            dataframe=pd.DataFrame(records).set_index("span_id"),
            annotation_name="repro_fidelity", annotator_kind="LLM")
    # repeat the same shape for root_cause_correctness + honesty (CODE) annotations.
```

> The `get_spans_dataframe` / `log_span_annotations_dataframe` column names must match what
> Task 0 recorded. If the verified query API differs, fix `_phoenix_span_lookup` /
> `_log_to_spans` accordingly — the pure `build_eval_dataframe` is the contract the test pins.

- [ ] **Step 4: Run pure test + wire the inline hook**

Run: `.venv/bin/pytest tests/test_eval_run_eval.py -v`
Expected: PASS.

Then in `scripts/phase7_traced_run.py`, replace the `# 7B eval hook` comment with a real call
inside the `with RunTrace(...)` block, after the loop reaches terminal and **before**
disconnect (the root span must still be open so annotations attach to live spans):

```python
        from triage.eval.run_eval import run_eval
        try:
            scored = run_eval(cfg, repro_state, artifacts,
                              hypothesis_root_cause="")  # harness fills if it tracks the diagnosis
            print("[phase7] eval scored attempts:\n", scored[[
                "attempt_number", "repro_fidelity_label", "root_cause_label"]]
                  if not scored.empty else "(none)")
        except Exception as exc:  # noqa: BLE001 — eval must never wedge the demo
            print(f"[phase7] eval step failed (non-fatal): {exc}")
```

Create `scripts/phase7_eval.py` as a thin standalone that loads a prior run dir + re-runs
`run_eval` against the existing Phoenix project (for re-scoring without a fresh browser run).

- [ ] **Step 5: Run full suite + commit**

Run: `.venv/bin/pytest -q`
Expected: PASS (no regressions; new eval tests green).

```bash
git add triage/eval/run_eval.py scripts/phase7_traced_run.py scripts/phase7_eval.py tests/test_eval_run_eval.py
git commit -m "feat(phase7b): per-attempt eval scored + logged to repro_attempt spans, inline"
```

- [ ] **Step 6: Live smoke (manual — real keys + network)**

Run: `.venv/bin/python scripts/phase7_traced_run.py --force-retry`
Expected: in Phoenix, attempt-1 `repro_attempt` span carries `repro_fidelity=not_reproduced`
and attempt-2 carries `reproduced`; root-cause + honesty annotations present. The score flip
is the on-screen "used Arize to improve" artifact. **Confirm scores are real LLM/code outputs,
not stubs.**

---

## Self-Review (Plan 7B)

- **Spec coverage:** §4.2 ground truth → Task 1; LLM judges → Task 2; code honesty check →
  Task 3; per-attempt scoring + log-to-spans + inline wiring → Task 4. Drift verification (§2)
  → Task 0.
- **Placeholder scan:** the `_log_to_spans` "repeat the same shape" comment is a concrete
  instruction (the record-building pattern is shown directly above it), not a TODO. All steps
  carry runnable code/commands.
- **Type consistency:** `build_fidelity_input`/`build_root_cause_input` return `{input,output}` /
  `{input,reference,output}` consistently used in Tasks 2 & 4; `FIDELITY_CHOICES`/`ROOT_CAUSE_CHOICES`,
  `honesty_check`/`HonestyResult`, `build_eval_dataframe`/`score_attempts`/`run_eval` names match
  across tasks. Consumes 7A's `RunArtifacts.load_attempts()` + `repro_attempt`/`attempt.number`
  exactly as 7A produces them.
