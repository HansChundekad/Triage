"""The backend-agnostic seam: fetch_prior_run_history dispatches to the active backend."""
import pytest

import triage.memory.history as history
from triage.memory.types import PriorAttempt


def test_phoenix_backend_is_default_and_delegates(monkeypatch):
    sentinel = [PriorAttempt("A", 1, "2026-06-20T10:00:01Z", True, "reproduced", 1.0)]
    captured = {}

    def _fake(cfg, *, issue_url, limit):
        captured["issue_url"] = issue_url
        captured["limit"] = limit
        return sentinel

    assert history.TRACE_BACKEND == "phoenix"  # instrumentation still on Phoenix today
    monkeypatch.setattr("triage.memory.backends.phoenix.fetch_prior_run_history", _fake)
    out = history.fetch_prior_run_history(object(), issue_url="https://issue/X", limit=3)
    assert out is sentinel
    assert captured == {"issue_url": "https://issue/X", "limit": 3}


def test_ax_backend_selected_delegates_to_ax_stub(monkeypatch):
    # When the migration flips TRACE_BACKEND to "ax", the seam routes there. The stub
    # raises NotImplementedError until wired — which the facade guards into a no-op.
    monkeypatch.setattr(history, "TRACE_BACKEND", "ax")
    with pytest.raises(NotImplementedError):
        history.fetch_prior_run_history(object(), issue_url="https://issue/X")


def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setattr(history, "TRACE_BACKEND", "nope")
    with pytest.raises(ValueError):
        history.fetch_prior_run_history(object(), issue_url="https://issue/X")
