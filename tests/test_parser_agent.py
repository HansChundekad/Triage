from __future__ import annotations

from types import SimpleNamespace

from triage.parser_agent.agent import format_steps_message, sender_agent_name
from triage.shared.band import ReproStepsPayload


def _fake_cfg() -> SimpleNamespace:
    return SimpleNamespace(
        band_parser=SimpleNamespace(agent_id="parser-id"),
        band_repro=SimpleNamespace(agent_id="repro-id"),
        band_hypothesis=SimpleNamespace(agent_id="hypothesis-id"),
    )


def test_format_steps_message_mentions_repro_and_numbers_steps():
    payload = ReproStepsPayload(
        issue_url="https://github.com/o/r/issues/7",
        steps=["Add a task named test", "Delete the task", "Confirm deletion"],
    )
    msg = format_steps_message(payload)

    assert msg.startswith("@ReproAgent")
    assert "https://github.com/o/r/issues/7" in msg
    assert "1. Add a task named test" in msg
    assert "2. Delete the task" in msg
    assert "3. Confirm deletion" in msg


def test_sender_agent_name_maps_known_ids():
    cfg = _fake_cfg()
    assert sender_agent_name("repro-id", cfg) == "ReproAgent"
    assert sender_agent_name("hypothesis-id", cfg) == "HypothesisAgent"
    assert sender_agent_name("parser-id", cfg) == "ParserAgent"


def test_sender_agent_name_returns_none_for_unknown():
    assert sender_agent_name("nobody", _fake_cfg()) is None
