"""Unit tests for ParserAgent echo logic (Phase 3 — no live Band)."""
from __future__ import annotations

from types import SimpleNamespace

from triage.parser_agent.echo import (
    PLACEHOLDER_STEPS,
    build_repro_steps_payload,
    format_steps_message,
    sender_agent_name,
)
from triage.shared.band import ReproStepsPayload


def _fake_cfg() -> SimpleNamespace:
    """Duck-typed stand-in for Config — only the three agent_ids are read."""
    return SimpleNamespace(
        band_parser=SimpleNamespace(agent_id="parser-id"),
        band_repro=SimpleNamespace(agent_id="repro-id"),
        band_hypothesis=SimpleNamespace(agent_id="hypothesis-id"),
    )


def test_placeholder_steps_are_the_four_echo_steps():
    assert PLACEHOLDER_STEPS == [
        "focus input",
        "type task",
        "click add",
        "click delete",
    ]


def test_build_repro_steps_payload_uses_placeholder_steps():
    payload = build_repro_steps_payload("https://example.com/issue/1")
    assert isinstance(payload, ReproStepsPayload)
    assert payload.issue_url == "https://example.com/issue/1"
    assert payload.steps == PLACEHOLDER_STEPS
    # must be a copy, not the shared module-level list
    assert payload.steps is not PLACEHOLDER_STEPS


def test_format_steps_message_mentions_repro_and_counts_steps():
    payload = build_repro_steps_payload("https://example.com/issue/1")
    msg = format_steps_message(payload)
    assert "@ReproAgent" in msg
    assert "extracted 4 steps" in msg
    assert "focus input, type task, click add, click delete" in msg
    assert "https://example.com/issue/1" in msg


def test_sender_agent_name_maps_known_ids():
    cfg = _fake_cfg()
    assert sender_agent_name("repro-id", cfg) == "ReproAgent"
    assert sender_agent_name("hypothesis-id", cfg) == "HypothesisAgent"
    assert sender_agent_name("parser-id", cfg) == "ParserAgent"


def test_sender_agent_name_returns_none_for_unknown():
    assert sender_agent_name("nobody", _fake_cfg()) is None
