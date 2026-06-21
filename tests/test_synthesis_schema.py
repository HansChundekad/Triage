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


def test_roundtrip_with_null_eval_scores():
    d = _valid_dict()
    d["eval_scores"] = None
    report = ReproReport.from_dict(d)
    assert report.eval_scores is None
    assert report.to_dict() == d
    validate_report(report.to_dict())


def test_published_schema_file_matches_module():
    published = json.loads(Path("docs/superpowers/specs/phase7-report.schema.json").read_text())
    assert published == REPORT_JSON_SCHEMA  # lockstep contract
