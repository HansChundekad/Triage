from starlette.testclient import TestClient

from backend.run_manager import (
    normalize_message,
    normalize_event,
    report_event_data,
    build_report_dict,
)
from triage.synthesis.schema import validate_report
from triage.tracing.artifacts import RunArtifacts


def test_normalize_message_shape():
    ev = normalize_message("ParserAgent", ["ReproAgent"], "extracted 4 steps")
    assert ev["type"] == "message"
    assert ev["from"] == "ParserAgent"
    assert ev["to"] == ["ReproAgent"]
    assert ev["text"] == "extracted 4 steps"
    assert "ts" in ev


def test_normalize_event_maps_browser_step():
    ev = normalize_event("ReproAgent", "focus input", "task", None)
    assert ev["type"] == "step"
    assert ev["agent"] == "ReproAgent"
    assert ev["kind"] == "browser"          # "task" → browser
    assert ev["text"] == "focus input"


def test_app_replays_list_endpoint():
    from backend.server import app
    client = TestClient(app)
    r = client.get("/api/replays")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# --------------------------------------------------------------------------- #
# Report-schema contract: the backend must emit the canonical Arize ReproReport
# (triage.synthesis is the single source of truth) — never the old camelCase
# placeholder shape.
# --------------------------------------------------------------------------- #
_CANON_MODEL_OUTPUT = {
    "verdict": "reproduced",
    "repro_steps": [
        {"n": 1, "action": "Type a task and click Add", "status": "ok",
         "screenshot_ref": "screenshots/attempt2_step1.png"},
        {"n": 2, "action": "Delete the task and confirm", "status": "crash",
         "screenshot_ref": "screenshots/attempt2_step2.png"},
    ],
    "root_cause": {
        "hypothesis": "Render reads items[0] after the last item is deleted",
        "mechanism": "items[0] dereferences undefined once the array is empty",
        "confidence": "high",
    },
    "evidence": {
        "console_error": "TypeError: Cannot read properties of undefined (reading '0')",
        "blank_screen": True,
        "body_snippet": "",
    },
}


def _fake_synthesize(cfg, artifacts, *, client, issue, hypothesis_root_cause,
                     eval_scores=None, run_trace=None):
    """Stand in for the real Claude call: assemble a genuine, schema-valid
    ReproReport from a fixed model output + the run's real artifacts."""
    from triage.synthesis.synthesize import assemble_report
    report = assemble_report(
        _CANON_MODEL_OUTPUT, issue=issue, attempts=artifacts.load_attempts(),
        eval_scores=eval_scores, now="2026-06-20T00:00:00Z",
    )
    return artifacts.write_report(report.to_dict())


def test_build_report_dict_emits_canonical_reproreport(tmp_path, monkeypatch):
    """The reconciled backend produces the Arize ReproReport: snake_case,
    per-step status, root_cause.mechanism, real session_replay_url, eval_scores —
    and none of the old camelCase placeholder keys."""
    import backend.run_manager as rm

    artifacts = RunArtifacts(tmp_path)
    artifacts.record_attempt({
        "attempt": 1, "steps": ["type a task", "click Add", "delete", "confirm"],
        "evidence": ["step 4 act: OK — clicked confirm"],
        "console_errors": ["TypeError: Cannot read properties of undefined (reading '0')"],
        "session_url": "https://www.browserbase.com/sessions/abc",
        "bug_detected": True,
    })
    monkeypatch.setattr(rm, "synthesize_run", _fake_synthesize)
    monkeypatch.setattr(
        rm, "_guarded_eval_scores",
        lambda *a, **k: {"repro_fidelity": 1.0, "root_cause_correctness": 1.0},
    )

    report = build_report_dict(
        None, artifacts, client=None,
        issue={"url": "https://github.com/org/repo/issues/1",
               "title": "blank page on delete", "summary": "deletes go blank"},
        hypothesis_root_cause="reads items[0] after delete",
    )

    validate_report(report)  # conforms to the canonical Arize schema
    assert report["verdict"] == "reproduced"
    assert report["repro_steps"][1]["status"] == "crash"
    assert report["root_cause"]["mechanism"]
    assert report["attempts"][0]["session_replay_url"] == "https://www.browserbase.com/sessions/abc"
    assert report["attempts"][0]["bug_detected"] is True
    assert report["eval_scores"]["repro_fidelity"] == 1.0
    assert "generated_at" in report
    for legacy in ("issueUrl", "reproSteps", "rootCause", "consoleErrors", "status"):
        assert legacy not in report, f"old placeholder key leaked: {legacy}"


def test_report_event_data_wraps_canonical_report():
    """report_event_data wraps the ReproReport under 'report' so the frontend's
    {type:"report", ...data} spread yields {type:"report", report:{…}}."""
    report = {"verdict": "reproduced", "issue": {"url": "u"}}
    assert report_event_data(report) == {"report": report}


def test_stream_unknown_run_returns_404():
    """I1: streaming an unknown run_id must return 404, not 500."""
    from backend.server import app
    client = TestClient(app)
    r = client.get("/api/runs/nonexistent/stream")
    assert r.status_code == 404
