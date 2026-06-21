from starlette.testclient import TestClient

from backend.run_manager import normalize_message, normalize_event, _Run, report_event_data


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


def test_report_event_data_wraps_run_report():
    """C1: report_event_data must wrap RunReport under a 'report' key so the
    frontend's {type:"report", ...data} spread yields {type:"report", report:{...}}."""
    run = _Run("testrunabc123", "https://github.com/org/repo/issues/42")
    run.reproduced = True
    run.last_hypothesis_text = "NullPointerException in handler"
    # Append a fake step event that carries a session_url (as normalize_event would).
    session_url = "https://www.browserbase.com/sessions/abc"
    run.buffer.append(("step", {
        "type": "step",
        "agent": "ReproAgent",
        "kind": "browser",
        "text": "navigated to page",
        "screenshot": None,
        "session_url": session_url,
        "ts": 0.0,
    }))

    result = report_event_data(run)

    # Top-level must have a "report" key.
    assert "report" in result, "missing top-level 'report' key"

    report = result["report"]
    # RunReport required keys.
    for key in ("issueUrl", "status", "verdict", "reproSteps", "rootCause", "attempts", "consoleErrors"):
        assert key in report, f"RunReport missing key: {key}"

    assert report["status"] == "reproduced"
    assert report["verdict"] == "Bug reproduced."
    assert report["issueUrl"] == "https://github.com/org/repo/issues/42"

    # Derived attempt must carry replayUrl from the session_url in buffer.
    assert len(report["attempts"]) == 1
    assert report["attempts"][0]["replayUrl"] == session_url


def test_stream_unknown_run_returns_404():
    """I1: streaming an unknown run_id must return 404, not 500."""
    from backend.server import app
    client = TestClient(app)
    r = client.get("/api/runs/nonexistent/stream")
    assert r.status_code == 404
