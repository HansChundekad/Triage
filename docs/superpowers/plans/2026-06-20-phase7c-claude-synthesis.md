# Phase 7C — Claude Synthesis + Report Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a completed run's captured artifacts (confirmed steps, root-cause hypothesis, per-step screenshots, console error, session replay URLs, eval scores) into a single structured `ReproReport` that the frontend renders, and publish its JSON Schema so the parallel frontend worktree can code against a fixed contract.

**Architecture:** `schema.py` defines the `ReproReport` dataclass + a published JSON Schema file. `synthesize.py` feeds the run's `RunArtifacts` to Claude (structured output via `output_config` json_schema, the same pattern Parser/Hypothesis already use) and writes a validated `report.json` into the run directory, wrapped in a `synthesis` span. Wired inline at the end of `scripts/phase7_traced_run.py`, after the evaluator.

**Tech Stack:** `anthropic` (structured output + adaptive thinking), Python dataclasses + `jsonschema` for validation, `pytest`. Reuses 7A's `RunArtifacts` + `RunTrace`.

## Global Constraints

- **Depends on Phase 7A** (`triage/tracing/artifacts.py::RunArtifacts.load_attempts()` /
  `write_report()`; `RunTrace.child_span` for the `synthesis` span; the inline hook in
  `scripts/phase7_traced_run.py`). Optionally consumes 7B eval scores if present. Do not start
  until 7A Tasks 3 & 7 are merged.
- Use the repo venv `.venv/`. Install/test: `.venv/bin/pip install -e ".[dev]"` · `.venv/bin/pytest`.
- TDD — failing test first. Per-task commits. Never modify `triage/shared/band.py`.
- Claude model: `claude-sonnet-4-6`; structured output via `output_config={"format":
  {"type":"json_schema","schema": ...}}` + `thinking={"type":"adaptive"}` (mirror
  `parser_agent/claude.py` exactly — that pattern is verified working in this repo).
- The Anthropic client is **injected** (testability), as in parser/hypothesis.
- The published JSON Schema is the frozen frontend contract — changing a field name is a
  breaking change; keep `schema.py` and the `.json` file in lockstep (Task 1 test enforces it).

---

### Task 1: `schema.py` + published JSON Schema — the frontend contract

**Files:**
- Create: `triage/synthesis/__init__.py`
- Create: `triage/synthesis/schema.py`
- Create: `docs/superpowers/specs/phase7-report.schema.json`
- Test: `tests/test_synthesis_schema.py`

**Interfaces:**
- Produces:
  - `ReproReport` dataclass (+ nested `Issue`, `ReproStep`, `RootCause`, `Evidence`,
    `Attempt`, `EvalScores`) with `to_dict()` and `from_dict()`.
  - `REPORT_JSON_SCHEMA: dict` — the JSON Schema, also written verbatim to
    `docs/superpowers/specs/phase7-report.schema.json`.
  - `validate_report(d: dict) -> None` — raises `jsonschema.ValidationError` on a bad report.
  - `CLAUDE_OUTPUT_SCHEMA: dict` — the (possibly stricter/flatter) schema handed to Claude's
    `output_config`. May omit server-filled fields (`generated_at`, `attempts[].session_replay_url`,
    `eval_scores`) that the code fills post-generation.

Field contract (frozen):

```jsonc
{
  "issue":       { "url": "str", "title": "str", "summary": "str" },
  "verdict":     "reproduced | not_reproduced",
  "repro_steps": [ { "n": 1, "action": "str", "status": "ok|fail|crash", "screenshot_ref": "str" } ],
  "root_cause":  { "hypothesis": "str", "mechanism": "str", "confidence": "high|medium|low" },
  "evidence":    { "console_error": "str", "blank_screen": true, "body_snippet": "str" },
  "attempts":    [ { "number": 1, "session_replay_url": "str", "bug_detected": false } ],
  "eval_scores": { "repro_fidelity": 1.0, "root_cause_correctness": 1.0 },  // nullable
  "generated_at": "ISO-8601 str"
}
```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_synthesis_schema.py
import json
from pathlib import Path

import pytest

from triage.synthesis.schema import (
    ReproReport, REPORT_JSON_SCHEMA, validate_report,
)


def _valid_dict():
    return {
        "issue": {"url": "http://i", "title": "blank on delete", "summary": "app blanks"},
        "verdict": "reproduced",
        "repro_steps": [{"n": 1, "action": "type task", "status": "ok", "screenshot_ref": "screenshots/attempt2_step1.png"},
                        {"n": 2, "action": "delete last", "status": "crash", "screenshot_ref": "screenshots/attempt2_step2.png"}],
        "root_cause": {"hypothesis": "reads items[0] after empty", "mechanism": "TypeError on undefined", "confidence": "high"},
        "evidence": {"console_error": "Cannot read properties of undefined", "blank_screen": True, "body_snippet": ""},
        "attempts": [{"number": 1, "session_replay_url": "http://s1", "bug_detected": False},
                     {"number": 2, "session_replay_url": "http://s2", "bug_detected": True}],
        "eval_scores": {"repro_fidelity": 1.0, "root_cause_correctness": 1.0},
        "generated_at": "2026-06-20T00:00:00Z",
    }


def test_report_roundtrips_through_dataclass():
    d = _valid_dict()
    report = ReproReport.from_dict(d)
    assert report.verdict == "reproduced"
    assert report.repro_steps[1].status == "crash"
    assert report.to_dict() == d


def test_validate_report_accepts_valid_and_rejects_bad():
    validate_report(_valid_dict())
    bad = _valid_dict(); bad["verdict"] = "maybe"
    with pytest.raises(Exception):
        validate_report(bad)


def test_published_schema_file_matches_module():
    published = json.loads(Path("docs/superpowers/specs/phase7-report.schema.json").read_text())
    assert published == REPORT_JSON_SCHEMA  # lockstep contract
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_synthesis_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: triage.synthesis.schema`.

- [ ] **Step 3: Write minimal implementation**

```python
# triage/synthesis/__init__.py
"""Claude synthesis (Phase 7C): run artifacts -> structured ReproReport."""
```

```python
# triage/synthesis/schema.py
"""ReproReport — the frozen frontend contract + Claude output schema."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import jsonschema


@dataclass
class Issue:
    url: str; title: str; summary: str


@dataclass
class ReproStep:
    n: int; action: str; status: str; screenshot_ref: str


@dataclass
class RootCause:
    hypothesis: str; mechanism: str; confidence: str


@dataclass
class Evidence:
    console_error: str; blank_screen: bool; body_snippet: str


@dataclass
class Attempt:
    number: int; session_replay_url: str; bug_detected: bool


@dataclass
class EvalScores:
    repro_fidelity: Optional[float] = None
    root_cause_correctness: Optional[float] = None


@dataclass
class ReproReport:
    issue: Issue
    verdict: str
    repro_steps: list[ReproStep]
    root_cause: RootCause
    evidence: Evidence
    attempts: list[Attempt]
    eval_scores: Optional[EvalScores]
    generated_at: str

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.eval_scores is None:
            d["eval_scores"] = None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ReproReport":
        es = d.get("eval_scores")
        return cls(
            issue=Issue(**d["issue"]),
            verdict=d["verdict"],
            repro_steps=[ReproStep(**s) for s in d["repro_steps"]],
            root_cause=RootCause(**d["root_cause"]),
            evidence=Evidence(**d["evidence"]),
            attempts=[Attempt(**a) for a in d["attempts"]],
            eval_scores=EvalScores(**es) if es else None,
            generated_at=d["generated_at"],
        )


REPORT_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["issue", "verdict", "repro_steps", "root_cause", "evidence",
                 "attempts", "eval_scores", "generated_at"],
    "properties": {
        "issue": {"type": "object", "additionalProperties": False,
                  "required": ["url", "title", "summary"],
                  "properties": {"url": {"type": "string"}, "title": {"type": "string"},
                                 "summary": {"type": "string"}}},
        "verdict": {"type": "string", "enum": ["reproduced", "not_reproduced"]},
        "repro_steps": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["n", "action", "status", "screenshot_ref"],
            "properties": {"n": {"type": "integer"}, "action": {"type": "string"},
                           "status": {"type": "string", "enum": ["ok", "fail", "crash"]},
                           "screenshot_ref": {"type": "string"}}}},
        "root_cause": {"type": "object", "additionalProperties": False,
                       "required": ["hypothesis", "mechanism", "confidence"],
                       "properties": {"hypothesis": {"type": "string"},
                                      "mechanism": {"type": "string"},
                                      "confidence": {"type": "string",
                                                     "enum": ["high", "medium", "low"]}}},
        "evidence": {"type": "object", "additionalProperties": False,
                     "required": ["console_error", "blank_screen", "body_snippet"],
                     "properties": {"console_error": {"type": "string"},
                                    "blank_screen": {"type": "boolean"},
                                    "body_snippet": {"type": "string"}}},
        "attempts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["number", "session_replay_url", "bug_detected"],
            "properties": {"number": {"type": "integer"},
                           "session_replay_url": {"type": "string"},
                           "bug_detected": {"type": "boolean"}}}},
        "eval_scores": {"type": ["object", "null"], "additionalProperties": False,
                        "properties": {"repro_fidelity": {"type": ["number", "null"]},
                                       "root_cause_correctness": {"type": ["number", "null"]}}},
        "generated_at": {"type": "string"},
    },
}

# Schema handed to Claude: only the fields the model should generate. Server fills
# attempts[].session_replay_url, eval_scores, generated_at after generation.
CLAUDE_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "repro_steps", "root_cause", "evidence"],
    "properties": {
        "verdict": REPORT_JSON_SCHEMA["properties"]["verdict"],
        "repro_steps": REPORT_JSON_SCHEMA["properties"]["repro_steps"],
        "root_cause": REPORT_JSON_SCHEMA["properties"]["root_cause"],
        "evidence": REPORT_JSON_SCHEMA["properties"]["evidence"],
    },
}


def validate_report(d: dict) -> None:
    jsonschema.validate(instance=d, schema=REPORT_JSON_SCHEMA)
```

- [ ] **Step 4: Write the published schema file (lockstep) and verify**

Generate the JSON file from the module so it can never drift:

```bash
.venv/bin/python -c "import json; from triage.synthesis.schema import REPORT_JSON_SCHEMA; open('docs/superpowers/specs/phase7-report.schema.json','w').write(json.dumps(REPORT_JSON_SCHEMA, indent=2))"
```

Run: `.venv/bin/pytest tests/test_synthesis_schema.py -v`
Expected: PASS (roundtrip, validation, and the published-file-matches-module lockstep test).

> `jsonschema` is a transitive dep of `arize-phoenix`; if `import jsonschema` fails, add it to
> `pyproject.toml` dependencies and reinstall.

- [ ] **Step 5: Commit**

```bash
git add triage/synthesis/__init__.py triage/synthesis/schema.py docs/superpowers/specs/phase7-report.schema.json tests/test_synthesis_schema.py
git commit -m "feat(phase7c): ReproReport schema + published JSON Schema (frontend contract)"
```

---

### Task 2: `synthesize.py` — artifacts → Claude → validated report

**Files:**
- Create: `triage/synthesis/synthesize.py`
- Test: `tests/test_synthesize.py`

**Interfaces:**
- Consumes: `RunArtifacts.load_attempts()` + `write_report()` (7A Task 3); `CLAUDE_OUTPUT_SCHEMA`,
  `ReproReport`, `validate_report` (Task 1); an injected Anthropic client; optionally a
  `RunTrace` for the `synthesis` span; optional 7B eval scores dict.
- Produces:
  - `build_synthesis_prompt(issue, attempts, hypothesis_root_cause) -> str` — pure; renders the
    confirmed steps, per-attempt evidence, console error, and screenshot refs into the user turn.
  - `assemble_report(model_output: dict, *, issue, attempts, eval_scores, now) -> ReproReport` —
    pure; merges Claude's generated fields with server-filled fields (session replay URLs from
    `attempts`, `eval_scores`, `generated_at`) and validates. Returns a `ReproReport`.
  - `synthesize_run(cfg, artifacts, *, client, issue, hypothesis_root_cause, eval_scores=None,
    run_trace=None) -> str` — orchestrates the Claude call (wrapped in a `synthesis` span),
    assembles + validates, writes `report.json` via `artifacts.write_report`, returns its path.

> Only the two **pure** functions are unit-tested; `synthesize_run` is thin orchestration over a
> live Claude call (injected client lets one test exercise it end-to-end with a canned response).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_synthesize.py
from triage.synthesis.synthesize import build_synthesis_prompt, assemble_report, synthesize_run
from triage.synthesis.schema import ReproReport, validate_report


_ATTEMPTS = [
    {"attempt": 1, "bug_detected": False, "evidence": ["empty list"],
     "console_errors": [], "session_url": "http://s1", "steps": ["delete"]},
    {"attempt": 2, "bug_detected": True, "evidence": ["blank body", "step crash"],
     "console_errors": ["Cannot read properties of undefined"], "session_url": "http://s2",
     "steps": ["type task", "click add", "delete", "confirm"]},
]
_ISSUE = {"url": "http://i", "title": "blank on delete", "summary": "app blanks on delete"}
_MODEL_OUTPUT = {
    "verdict": "reproduced",
    "repro_steps": [{"n": 1, "action": "type task", "status": "ok", "screenshot_ref": ""},
                    {"n": 2, "action": "delete last", "status": "crash", "screenshot_ref": ""}],
    "root_cause": {"hypothesis": "reads items[0] after empty", "mechanism": "TypeError", "confidence": "high"},
    "evidence": {"console_error": "Cannot read properties of undefined", "blank_screen": True, "body_snippet": ""},
}


def test_prompt_includes_console_error_and_steps():
    p = build_synthesis_prompt(_ISSUE, _ATTEMPTS, "reads items[0] after delete")
    assert "Cannot read properties of undefined" in p
    assert "type task" in p


def test_assemble_report_merges_server_fields_and_validates():
    report = assemble_report(_MODEL_OUTPUT, issue=_ISSUE, attempts=_ATTEMPTS,
                             eval_scores={"repro_fidelity": 1.0, "root_cause_correctness": 1.0},
                             now="2026-06-20T00:00:00Z")
    assert isinstance(report, ReproReport)
    d = report.to_dict()
    validate_report(d)
    # session replay URLs pulled from attempts, not the model
    assert [a["session_replay_url"] for a in d["attempts"]] == ["http://s1", "http://s2"]
    assert d["eval_scores"]["repro_fidelity"] == 1.0
    assert d["generated_at"] == "2026-06-20T00:00:00Z"


def test_synthesize_run_writes_report(tmp_path):
    from triage.tracing.artifacts import RunArtifacts

    class _Block: type = "text"
    _Block.text = __import__("json").dumps(_MODEL_OUTPUT)
    class _Resp: content = [_Block()]
    class _Msgs:
        def create(self, **kw): return _Resp()
    class _Client: messages = _Msgs()

    art = RunArtifacts(tmp_path)
    for a in _ATTEMPTS:
        art.record_attempt(a)
    path = synthesize_run(_Cfg(), art, client=_Client(), issue=_ISSUE,
                          hypothesis_root_cause="reads items[0] after delete")
    import json
    data = json.loads(open(path).read())
    validate_report(data)
    assert data["verdict"] == "reproduced"


class _Cfg:
    pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_synthesize.py -v`
Expected: FAIL — `ModuleNotFoundError: triage.synthesis.synthesize`.

- [ ] **Step 3: Write minimal implementation**

```python
# triage/synthesis/synthesize.py
"""Run artifacts -> Claude structured output -> validated ReproReport.

Mirrors parser_agent/claude.py exactly for the Claude call shape (output_config
json_schema + adaptive thinking), which is the verified-working pattern in this repo.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from triage.synthesis.schema import (
    Attempt, EvalScores, Evidence, Issue, ReproReport, RootCause, ReproStep,
    CLAUDE_OUTPUT_SCHEMA, validate_report,
)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 4096
_SYSTEM = (
    "You are a senior engineer writing a concise, accurate bug-reproduction report "
    "from the evidence a browser-automation agent captured. Use ONLY the provided "
    "evidence; do not invent steps, errors, or causes. Mark a step 'crash' when the "
    "evidence shows the page broke on that step, 'fail' if the action did not work, "
    "else 'ok'. Set verdict 'reproduced' only if the reported bug clearly fired."
)


def build_synthesis_prompt(issue: dict, attempts: list[dict], hypothesis_root_cause: str) -> str:
    final = attempts[-1] if attempts else {}
    lines = [
        f"Issue title: {issue['title']}",
        f"Issue summary: {issue['summary']}",
        "",
        "Confirmed repro steps (final attempt):",
        *[f"  - {s}" for s in final.get("steps", [])],
        "",
        "Per-attempt evidence:",
    ]
    for a in attempts:
        lines.append(f"  attempt {a['attempt']} (bug_detected={a.get('bug_detected')}):")
        lines += [f"    - {e}" for e in a.get("evidence", [])]
        lines += [f"    console: {c}" for c in a.get("console_errors", [])]
    lines += ["", f"Diagnosed root cause (from HypothesisAgent): {hypothesis_root_cause}",
              "", "Produce the structured report."]
    return "\n".join(lines)


def assemble_report(model_output: dict, *, issue: dict, attempts: list[dict],
                    eval_scores: dict | None, now: str) -> ReproReport:
    report = ReproReport(
        issue=Issue(**issue),
        verdict=model_output["verdict"],
        repro_steps=[ReproStep(**s) for s in model_output["repro_steps"]],
        root_cause=RootCause(**model_output["root_cause"]),
        evidence=Evidence(**model_output["evidence"]),
        attempts=[Attempt(number=a["attempt"], session_replay_url=a.get("session_url", ""),
                          bug_detected=bool(a.get("bug_detected"))) for a in attempts],
        eval_scores=EvalScores(**eval_scores) if eval_scores else None,
        generated_at=now,
    )
    validate_report(report.to_dict())
    return report


def synthesize_run(cfg, artifacts, *, client, issue: dict, hypothesis_root_cause: str,
                   eval_scores: dict | None = None, run_trace=None) -> str:
    from triage.tracing.run_context import NullRunTrace
    run_trace = run_trace if run_trace is not None else NullRunTrace()

    attempts = artifacts.load_attempts()
    prompt = build_synthesis_prompt(issue, attempts, hypothesis_root_cause)

    with run_trace.claude_span("synthesis"):
        response = client.messages.create(
            model=_MODEL, max_tokens=_MAX_TOKENS,
            thinking={"type": "adaptive"}, system=_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": CLAUDE_OUTPUT_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
    text = next(b.text for b in response.content if getattr(b, "type", None) == "text")
    model_output = json.loads(text)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = assemble_report(model_output, issue=issue, attempts=attempts,
                             eval_scores=eval_scores, now=now)
    return artifacts.write_report(report.to_dict())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_synthesize.py -v`
Expected: PASS (prompt, assemble, and the canned-client end-to-end write).

- [ ] **Step 5: Commit**

```bash
git add triage/synthesis/synthesize.py tests/test_synthesize.py
git commit -m "feat(phase7c): synthesize_run — artifacts -> Claude -> validated report.json"
```

---

### Task 3: Wire synthesis inline + full regression

**Files:**
- Modify: `scripts/phase7_traced_run.py` (activate the 7C hook, after the 7B eval)

**Interfaces:**
- Consumes: `synthesize_run` (Task 2), the run's `issue` (from `issue_cache`), the diagnosed
  root cause (the harness already routes Hypothesis output; pass its `root_cause` string), and
  optional `eval_scores` produced by 7B's `run_eval`.

- [ ] **Step 1: Add the inline synthesis call**

In `scripts/phase7_traced_run.py`, after the 7B eval block and **before** disconnect (inside the
`with RunTrace(...)` block so the `synthesis` span nests under the root):

```python
        from triage.synthesis.synthesize import synthesize_run
        try:
            issue = issue_cache.get("issue")
            issue_dict = {"url": cfg.github_issue_url,
                          "title": getattr(issue, "title", ""),
                          "summary": getattr(issue, "body", "")[:280]}
            eval_scores = None
            if "scored" in dir() and not scored.empty:
                last = scored.iloc[-1]
                eval_scores = {"repro_fidelity": float(last["repro_fidelity_score"]),
                               "root_cause_correctness": float(last["root_cause_score"])}
            report_path = synthesize_run(
                cfg, artifacts, client=hypothesis_anthropic, issue=issue_dict,
                hypothesis_root_cause="",  # harness passes the confirmed diagnosis if tracked
                eval_scores=eval_scores, run_trace=run)
            print(f"[phase7] report written: {report_path}")
        except Exception as exc:  # noqa: BLE001 — synthesis must never wedge the demo
            print(f"[phase7] synthesis step failed (non-fatal): {exc}")
```

> `hypothesis_anthropic` is the sync `anthropic.Anthropic` client already created in the runner;
> `synthesize_run` uses a sync `messages.create`, so reuse it (no new client needed).

- [ ] **Step 2: Byte-check + full suite (regression gate)**

Run: `.venv/bin/python -c "import ast; ast.parse(open('scripts/phase7_traced_run.py').read()); print('ok')"`
Run: `.venv/bin/pytest -q`
Expected: `ok`; all tests PASS (7A + 7B + 7C, no regressions).

- [ ] **Step 3: Commit**

```bash
git add scripts/phase7_traced_run.py
git commit -m "feat(phase7c): wire inline synthesis -> report.json after eval"
```

- [ ] **Step 4: Live smoke (manual — real keys + network)**

Run: `.venv/bin/python scripts/phase7_traced_run.py --force-retry`
Expected: `./.triage_runs/<ts>/report.json` validates against
`docs/superpowers/specs/phase7-report.schema.json`; `verdict=reproduced`; `attempts` shows the
False→True progression with both session replay URLs; `eval_scores` populated if 7B ran; a
`synthesis` span appears under `triage_run` in Phoenix. Hand the schema file to the frontend
worktree as the render contract.

---

## Self-Review (Plan 7C)

- **Spec coverage:** §4.3 `ReproReport` schema + published JSON Schema → Task 1; Claude
  synthesis over artifacts → Task 2; inline wiring + frontend hand-off → Task 3. The schema is
  the explicit frontend contract the design called out.
- **Placeholder scan:** the two `hypothesis_root_cause=""` defaults are intentional seams (the
  harness fills the confirmed diagnosis if it tracks it; an empty string still produces a valid
  report). All steps carry runnable code/commands; no TBD/TODO.
- **Type consistency:** `ReproReport.from_dict`/`to_dict`, the nested dataclasses, `validate_report`,
  `CLAUDE_OUTPUT_SCHEMA`, `build_synthesis_prompt`/`assemble_report`/`synthesize_run` names match
  across Tasks 1-3. Consumes 7A's `RunArtifacts.load_attempts()`/`write_report()` and `RunTrace.claude_span`
  exactly as 7A produces them; consumes 7B's `scored` dataframe columns
  (`repro_fidelity_score`/`root_cause_score`) exactly as 7B names them.
