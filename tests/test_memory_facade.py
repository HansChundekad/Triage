import types

import triage.memory as memory
from triage.memory.query import PriorAttempt


def _cfg(enabled):
    return types.SimpleNamespace(outer_loop_enabled=enabled,
                                 github_issue_url="https://issue/X")


def test_flag_off_returns_none_without_querying(monkeypatch):
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("must not query when flag is OFF")

    monkeypatch.setattr(memory, "query_prior_runs", _boom)
    assert memory.load_learned_context(_cfg(False)) is None
    assert called["n"] == 0


def test_flag_on_returns_distilled_hint(monkeypatch):
    prior = [PriorAttempt("A", 1, "not_reproduced", 0.0, False),
             PriorAttempt("A", 2, "reproduced", 1.0, True)]
    monkeypatch.setattr(memory, "query_prior_runs", lambda cfg, **k: prior)
    hint = memory.load_learned_context(_cfg(True))
    assert hint and "Prior-run memory" in hint


def test_query_failure_degrades_to_none(monkeypatch):
    def _raise(cfg, **k):
        raise RuntimeError("phoenix 401")

    monkeypatch.setattr(memory, "query_prior_runs", _raise)
    assert memory.load_learned_context(_cfg(True)) is None


def test_empty_history_returns_none(monkeypatch):
    monkeypatch.setattr(memory, "query_prior_runs", lambda cfg, **k: [])
    assert memory.load_learned_context(_cfg(True)) is None
