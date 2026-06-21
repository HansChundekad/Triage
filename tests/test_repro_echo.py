import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from triage.repro_agent.echo import (
    format_result_message,
    _sender_is_hypothesis,
    handle_parser_message,
)
from triage.shared.band import ReproResultPayload


def test_format_result_message_bug_detected():
    result = ReproResultPayload(
        success=True,
        evidence=["step 1 ok", "detected: blank_body=True"],
        console_errors=["TypeError: Cannot read properties of undefined"],
        session_url="https://www.browserbase.com/sessions/abc123",
    )
    msg = format_result_message(result)
    assert "@hanschundekad/hypothesisagent" in msg
    assert "BUG REPRODUCED" in msg
    assert "abc123" in msg


def test_format_result_message_bug_not_reproduced():
    result = ReproResultPayload(
        success=False,
        evidence=["no crash observed"],
        console_errors=[],
        session_url="https://www.browserbase.com/sessions/xyz",
    )
    msg = format_result_message(result)
    assert "@hanschundekad/hypothesisagent" in msg
    assert "BUG NOT REPRODUCED" in msg
    assert "xyz" in msg


def test_sender_is_hypothesis():
    assert _sender_is_hypothesis("hanschundekad/hypothesisagent") is True
    assert _sender_is_hypothesis("HypothesisAgent") is True
    assert _sender_is_hypothesis("hanschundekad/parseragent") is False
    assert _sender_is_hypothesis(None) is False


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


def _fake_result():
    return ReproResultPayload(
        success=True,
        evidence=["Browserbase session: abc123", "Navigated to: http://localhost:3000"],
        console_errors=["TypeError: Cannot read properties of undefined"],
        session_url="https://www.browserbase.com/sessions/abc123",
    )


def test_handler_sends_one_message_to_hypothesis():
    agent = _FakeAgent()
    fake_cfg = MagicMock()
    with (
        patch("triage.repro_agent.echo.load_config", return_value=fake_cfg),
        patch("triage.repro_agent.echo.run_repro", new=AsyncMock(return_value=_fake_result())),
    ):
        asyncio.run(handle_parser_message(_msg("hanschundekad/parseragent"), agent))
    assert len(agent.messages) == 1
    mentions, text = agent.messages[0]
    assert mentions == ["HypothesisAgent"]
    assert "@hanschundekad/hypothesisagent" in text
    assert len(agent.events) == 2            # "Starting…" + "Repro complete…"
    assert agent.events[0][1] == "task"
    assert agent.events[1][1] == "task"


def test_handler_ignores_hypothesis_sender():
    agent = _FakeAgent()
    asyncio.run(handle_parser_message(_msg("hanschundekad/hypothesisagent"), agent))
    assert agent.messages == []              # no echo of a Hypothesis reply
    assert agent.events == []


def test_handler_browser_error_still_reports():
    """If run_repro raises, handler catches, sends error event, still messages HypothesisAgent."""
    agent = _FakeAgent()
    fake_cfg = MagicMock()
    with (
        patch("triage.repro_agent.echo.load_config", return_value=fake_cfg),
        patch(
            "triage.repro_agent.echo.run_repro",
            new=AsyncMock(side_effect=RuntimeError("CDP timeout")),
        ),
    ):
        asyncio.run(handle_parser_message(_msg("hanschundekad/parseragent"), agent))
    assert len(agent.messages) == 1
    mentions, text = agent.messages[0]
    assert mentions == ["HypothesisAgent"]
    assert "BUG NOT REPRODUCED" in text
    # events: "Starting…", "Browser execution error: …", "Repro complete…"
    event_types = [ev[1] for ev in agent.events]
    assert "task" in event_types
    assert "error" in event_types
