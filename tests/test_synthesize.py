"""Tests for triage.synthesis.synthesize — pure builders + canned-client write."""
from __future__ import annotations

import json

from triage.synthesis.synthesize import (
    build_synthesis_prompt, assemble_report, synthesize_run,
)
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
    assert "reads items[0] after delete" in p


def test_assemble_report_merges_server_fields_and_validates():
    report = assemble_report(_MODEL_OUTPUT, issue=_ISSUE, attempts=_ATTEMPTS,
                             eval_scores={"repro_fidelity": 1.0, "root_cause_correctness": 1.0},
                             now="2026-06-20T00:00:00Z")
    assert isinstance(report, ReproReport)
    d = report.to_dict()
    validate_report(d)
    # session replay URLs pulled from attempts, not the model
    assert [a["session_replay_url"] for a in d["attempts"]] == ["http://s1", "http://s2"]
    assert d["attempts"][0]["bug_detected"] is False
    assert d["attempts"][1]["bug_detected"] is True
    assert d["eval_scores"]["repro_fidelity"] == 1.0
    assert d["generated_at"] == "2026-06-20T00:00:00Z"


def test_assemble_report_without_eval_scores_is_valid():
    report = assemble_report(_MODEL_OUTPUT, issue=_ISSUE, attempts=_ATTEMPTS,
                             eval_scores=None, now="2026-06-20T00:00:00Z")
    d = report.to_dict()
    validate_report(d)
    assert d["eval_scores"] is None


def test_synthesize_run_writes_validated_report(tmp_path):
    from triage.tracing.artifacts import RunArtifacts

    class _Block:
        type = "text"
        text = json.dumps(_MODEL_OUTPUT)

    class _Resp:
        content = [_Block()]

    class _Msgs:
        def create(self, **kw):
            # confirm the schema is passed to Claude (structured output)
            assert kw["output_config"]["format"]["type"] == "json_schema"
            return _Resp()

    class _Client:
        messages = _Msgs()

    art = RunArtifacts(tmp_path)
    for a in _ATTEMPTS:
        art.record_attempt(a)

    path = synthesize_run(object(), art, client=_Client(), issue=_ISSUE,
                          hypothesis_root_cause="reads items[0] after delete")
    data = json.loads(open(path).read())
    validate_report(data)
    assert data["verdict"] == "reproduced"
    assert data["attempts"][1]["session_replay_url"] == "http://s2"
