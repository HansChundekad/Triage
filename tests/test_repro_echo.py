import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from triage.repro_agent.echo import format_result_message, make_repro_callback
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


class _FakeAgent:
    name = "ReproAgent"

    def __init__(self):
        self.messages = []  # list[(mentions, text)]
        self.events = []    # list[(content, event_type)]

    async def send_message(self, mentions, text):
        self.messages.append((mentions, text))

    async def send_event(self, content, event_type, metadata=None):
        self.events.append((content, event_type))


def _cfg():
    return SimpleNamespace(
        band_parser=SimpleNamespace(agent_id="parser-id"),
        band_hypothesis=SimpleNamespace(agent_id="hypo-id"),
    )


def _parser_msg():
    return SimpleNamespace(
        sender_name="hanschundekad/parseragent", sender_id="parser-id",
        chat_room_id="room-id",
        content="@ReproAgent steps:\n1. Open app\n2. Add todo\n3. Delete it",
    )


def _redirect_msg():
    return SimpleNamespace(
        sender_name="hanschundekad/hypothesisagent", sender_id="hypo-id",
        chat_room_id="room-id",
        content="@hanschundekad/reproagent retry with a slower delete (suspected cause: race)",
    )


def _fake_result():
    return ReproResultPayload(
        success=True,
        evidence=["Browserbase session: abc123", "Navigated to: http://localhost:3000"],
        console_errors=["TypeError: Cannot read properties of undefined"],
        session_url="https://www.browserbase.com/sessions/abc123",
    )


def test_parser_steps_trigger_one_attempt():
    agent = _FakeAgent()
    cb = make_repro_callback(_cfg())
    fake_run = AsyncMock(return_value=_fake_result())
    with patch("triage.repro_agent.echo.run_repro", new=fake_run):
        asyncio.run(cb(_parser_msg(), agent))
    assert fake_run.call_args.args[1] == ["Open app", "Add todo", "Delete it"]
    assert [m[0] for m in agent.messages] == [["HypothesisAgent"]]


def test_redirect_spawns_a_second_attempt_with_tweak():
    agent = _FakeAgent()
    cb = make_repro_callback(_cfg())
    fake_run = AsyncMock(return_value=_fake_result())
    with patch("triage.repro_agent.echo.run_repro", new=fake_run):
        asyncio.run(cb(_parser_msg(), agent))      # attempt 1
        asyncio.run(cb(_redirect_msg(), agent))    # attempt 2 (retry)
    assert fake_run.call_count == 2
    # second call carried the extracted tweak
    assert fake_run.call_args_list[1].kwargs.get("tweak") == "retry with a slower delete"
    # two results posted @HypothesisAgent (one per attempt)
    assert len(agent.messages) == 2


def test_redirect_before_any_steps_is_ignored():
    agent = _FakeAgent()
    cb = make_repro_callback(_cfg())
    fake_run = AsyncMock(return_value=_fake_result())
    with patch("triage.repro_agent.echo.run_repro", new=fake_run):
        asyncio.run(cb(_redirect_msg(), agent))
    # no steps yet -> nothing to retry
    assert fake_run.call_count == 0
    assert agent.messages == []


def test_attempt_browser_error_still_reports():
    """If run_repro raises, the attempt catches, sends an error event, and still
    messages HypothesisAgent with a BUG NOT REPRODUCED result."""
    agent = _FakeAgent()
    cb = make_repro_callback(_cfg())
    with patch(
        "triage.repro_agent.echo.run_repro",
        new=AsyncMock(side_effect=RuntimeError("CDP timeout")),
    ):
        asyncio.run(cb(_parser_msg(), agent))
    assert len(agent.messages) == 1
    mentions, text = agent.messages[0]
    assert mentions == ["HypothesisAgent"]
    assert "BUG NOT REPRODUCED" in text
    event_types = [ev[1] for ev in agent.events]
    assert "error" in event_types
