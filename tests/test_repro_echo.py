from triage.repro_agent.echo import (
    build_fake_result,
    format_result_message,
    _sender_is_hypothesis,
)
from triage.shared.band import ReproResultPayload


def test_build_fake_result_shape():
    result = build_fake_result()
    assert isinstance(result, ReproResultPayload)
    assert result.success is True              # placeholder: bug reproduced
    assert result.evidence                     # non-empty
    assert any("TypeError" in c for c in result.console_errors)
    assert "PLACEHOLDER" in result.session_url  # honest: not a real Browserbase session


def test_format_result_message_mentions_hypothesis():
    text = format_result_message(build_fake_result())
    assert "@hanschundekad/hypothesisagent" in text
    assert "TypeError" in text
    assert "BUG REPRODUCED" in text


def test_sender_is_hypothesis():
    assert _sender_is_hypothesis("hanschundekad/hypothesisagent") is True
    assert _sender_is_hypothesis("HypothesisAgent") is True
    assert _sender_is_hypothesis("hanschundekad/parseragent") is False
    assert _sender_is_hypothesis(None) is False


import asyncio
from types import SimpleNamespace

from triage.repro_agent.echo import handle_parser_message


class _FakeAgent:
    name = "ReproAgent"

    def __init__(self):
        self.messages = []  # list[(mentions, text)]
        self.events = []    # list[(content, event_type)]

    async def send_message(self, mentions, text):
        self.messages.append((mentions, text))

    async def send_event(self, content, event_type, metadata=None):
        self.events.append((content, event_type))


def _msg(sender_name):
    return SimpleNamespace(
        sender_name=sender_name,
        sender_id="peer-id",
        chat_room_id="room-id",
        content="1. Open app  2. Add todo  3. Delete it  4. observe blank screen",
    )


def test_handler_sends_one_message_to_hypothesis():
    agent = _FakeAgent()
    asyncio.run(handle_parser_message(_msg("hanschundekad/parseragent"), agent))
    assert len(agent.messages) == 1
    mentions, text = agent.messages[0]
    assert mentions == ["HypothesisAgent"]
    assert "@hanschundekad/hypothesisagent" in text
    assert len(agent.events) == 1            # one log event posted
    assert agent.events[0][1] == "task"


def test_handler_ignores_hypothesis_sender():
    agent = _FakeAgent()
    asyncio.run(handle_parser_message(_msg("hanschundekad/hypothesisagent"), agent))
    assert agent.messages == []              # no echo of a Hypothesis reply
    assert agent.events == []
