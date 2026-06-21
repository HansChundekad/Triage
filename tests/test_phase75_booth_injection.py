import asyncio
import types

from backend.run_manager import maybe_inject_learned_context


class _Agent:
    def __init__(self):
        self.sent = []

    async def send_message(self, mentions, text):
        self.sent.append((mentions, text))


def test_injects_hint_when_enabled(monkeypatch):
    import backend.run_manager as rm
    monkeypatch.setattr(rm, "load_learned_context", lambda cfg: "Prior-run memory: x")
    agent = _Agent()
    cfg = types.SimpleNamespace(outer_loop_enabled=True)
    hint = asyncio.run(maybe_inject_learned_context(cfg, agent))
    assert hint == "Prior-run memory: x"
    mentions, text = agent.sent[0]
    assert "ReproAgent" in mentions and "HypothesisAgent" in mentions
    assert "Prior-run memory: x" in text


def test_no_injection_when_disabled(monkeypatch):
    import backend.run_manager as rm
    monkeypatch.setattr(rm, "load_learned_context", lambda cfg: None)
    agent = _Agent()
    cfg = types.SimpleNamespace(outer_loop_enabled=False)
    hint = asyncio.run(maybe_inject_learned_context(cfg, agent))
    assert hint is None
    assert agent.sent == []
