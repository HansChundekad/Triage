"""Unit tests for the HypothesisAgent echo callback (no live network)."""
import asyncio
from types import SimpleNamespace

from triage.hypothesis_agent.agent import make_echo_callback, PLACEHOLDER_HYPOTHESIS

REPRO_ID = "repro-agent-id-123"


class FakeAgent:
    """Stand-in for BandAgent that records send_message calls."""

    name = "HypothesisAgent"

    def __init__(self):
        self.sent: list[tuple[list[str], str]] = []

    async def send_message(self, mentions, text):
        self.sent.append((mentions, text))


def _payload(sender_id, content="ran all 4 steps — blank screen + TypeError"):
    return SimpleNamespace(
        sender_id=sender_id,
        sender_name="ReproAgent",
        content=content,
    )


def test_echoes_placeholder_back_to_reproagent():
    cb = make_echo_callback(REPRO_ID)
    agent = FakeAgent()
    asyncio.run(cb(_payload(REPRO_ID), agent))

    assert len(agent.sent) == 1
    mentions, text = agent.sent[0]
    assert mentions == ["ReproAgent"]
    assert PLACEHOLDER_HYPOTHESIS.root_cause in text
    assert "Repro valid" in text


def test_ignores_messages_not_from_reproagent():
    cb = make_echo_callback(REPRO_ID)
    agent = FakeAgent()
    asyncio.run(cb(_payload("some-other-agent-id"), agent))

    assert agent.sent == []


def test_placeholder_has_no_redirect():
    # Phase 3 echo just acknowledges; the redirect capability arrives later.
    assert PLACEHOLDER_HYPOTHESIS.redirect is None
