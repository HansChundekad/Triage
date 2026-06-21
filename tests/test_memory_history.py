"""The backend-agnostic seam: fetch_prior_run_history dispatches to the active backend.

After the Phoenix->AX migration the default backend is "ax"; a per-call
`cfg.trace_backend` overrides it ("phoenix" selects the fallback adapter).
"""
import pytest

import triage.memory.history as history
from triage.memory.types import PriorAttempt


class _Cfg:
    def __init__(self, backend=None):
        if backend is not None:
            self.trace_backend = backend


def test_ax_is_default_backend_and_delegates(monkeypatch):
    sentinel = [PriorAttempt("A", 1, "2026-06-20T10:00:01Z", True, "reproduced", 1.0)]
    captured = {}

    def _fake(cfg, *, issue_url, limit):
        captured["issue_url"] = issue_url
        captured["limit"] = limit
        return sentinel

    assert history.TRACE_BACKEND == "ax"  # AX is primary post-migration
    monkeypatch.setattr("triage.memory.backends.ax.fetch_prior_run_history", _fake)
    # cfg without a trace_backend attr falls back to the module default (ax).
    out = history.fetch_prior_run_history(_Cfg(), issue_url="https://issue/X", limit=3)
    assert out is sentinel
    assert captured == {"issue_url": "https://issue/X", "limit": 3}


def test_phoenix_backend_selected_via_cfg_delegates(monkeypatch):
    sentinel = [PriorAttempt("B", 1, "2026-06-20T10:00:01Z", False, "", None)]

    def _fake(cfg, *, issue_url, limit):
        return sentinel

    monkeypatch.setattr("triage.memory.backends.phoenix.fetch_prior_run_history", _fake)
    out = history.fetch_prior_run_history(_Cfg("phoenix"), issue_url="https://issue/X")
    assert out is sentinel


def test_unknown_backend_raises():
    with pytest.raises(ValueError):
        history.fetch_prior_run_history(_Cfg("nope"), issue_url="https://issue/X")
