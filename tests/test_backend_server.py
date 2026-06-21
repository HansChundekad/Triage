from starlette.testclient import TestClient

from backend.run_manager import normalize_message, normalize_event


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
