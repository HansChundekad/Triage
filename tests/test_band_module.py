"""Unit tests for triage.shared.band — no live network calls."""
import pytest

from triage.shared.band import (
    BandAgent,
    HypothesisPayload,
    ReproResultPayload,
    ReproStepsPayload,
)


# --- Schema dataclasses ---

def test_repro_steps_payload_round_trips():
    p = ReproStepsPayload(
        issue_url="https://github.com/x/y/issues/1",
        steps=["click X", "delete Y"],
    )
    assert p.issue_url == "https://github.com/x/y/issues/1"
    assert p.steps == ["click X", "delete Y"]


def test_repro_steps_payload_empty_steps_default():
    p = ReproStepsPayload(issue_url="https://github.com/x/y/issues/2")
    assert p.steps == []


def test_repro_result_payload_round_trips():
    p = ReproResultPayload(
        success=False,
        evidence=["blank screen"],
        console_errors=["TypeError: Cannot read properties of undefined"],
        session_url="https://www.browserbase.com/sessions/abc123",
    )
    assert p.success is False
    assert len(p.console_errors) == 1
    assert "TypeError" in p.console_errors[0]


def test_repro_result_payload_defaults():
    p = ReproResultPayload(success=True)
    assert p.evidence == []
    assert p.console_errors == []
    assert p.session_url == ""


def test_hypothesis_payload_no_redirect():
    p = HypothesisPayload(root_cause="null dereference on empty list", redirect=None)
    assert p.redirect is None


def test_hypothesis_payload_with_redirect():
    p = HypothesisPayload(
        root_cause="race condition",
        redirect="retry with slower delete",
    )
    assert p.redirect == "retry with slower delete"


# --- BandAgent interface ---

def test_band_agent_raises_without_connect():
    agent = BandAgent("ParserAgent", agent_id="fake-id", api_key="fake-key")
    import asyncio

    with pytest.raises(RuntimeError, match="connect"):
        asyncio.run(agent.send_message(["ReproAgent"], "hello"))


def test_band_agent_send_message_requires_mentions():
    agent = BandAgent("ParserAgent", agent_id="fake-id", api_key="fake-key")
    # Patch _link and _room_id to bypass connection check
    agent._link = object()
    agent._room_id = "fake-room"
    import asyncio

    with pytest.raises(ValueError, match="mention"):
        asyncio.run(agent.send_message([], "hello"))


def test_band_agent_name_and_handle():
    agent = BandAgent("ReproAgent", agent_id="fake-id", api_key="fake-key")
    assert agent.name == "ReproAgent"
    assert "reproagent" in agent.handle
