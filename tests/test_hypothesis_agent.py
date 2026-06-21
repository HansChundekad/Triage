"""Unit tests for the HypothesisAgent diagnosis callback + routing (no network)."""
import asyncio
from types import SimpleNamespace

import triage.hypothesis_agent.agent as agent_mod
from triage.hypothesis_agent.agent import (
    route_diagnosis,
    format_diagnosis_message,
    make_diagnosis_callback,
)
from triage.hypothesis_agent.reasoning import Diagnosis
from triage.shared.band import HypothesisPayload

REPRO_ID = "repro-agent-id-123"


class FakeAgent:
    """Stand-in for BandAgent recording send_message / send_event calls."""

    name = "HypothesisAgent"

    def __init__(self):
        self.sent: list[tuple[list[str], str]] = []
        self.events: list[tuple[str, str]] = []

    async def send_message(self, mentions, text):
        self.sent.append((mentions, text))

    async def send_event(self, content, event_type, metadata=None):
        self.events.append((content, event_type))


def _payload(sender_id, content="verdict: BUG REPRODUCED ..."):
    return SimpleNamespace(sender_id=sender_id, sender_name="ReproAgent", content=content)


# --- routing -------------------------------------------------------------

def test_route_confirm_to_reproagent():
    d = Diagnosis(decision="confirm", root_cause="items[0] deref", redirect_instruction="")
    mentions, payload = route_diagnosis(d)
    assert mentions == ["ReproAgent"]
    assert isinstance(payload, HypothesisPayload)
    assert payload.root_cause == "items[0] deref"
    assert payload.redirect is None


def test_route_redirect_repro_to_reproagent():
    d = Diagnosis(
        decision="redirect_repro", root_cause="no crash", redirect_instruction="retry slower"
    )
    mentions, payload = route_diagnosis(d)
    assert mentions == ["ReproAgent"]
    assert payload.redirect == "retry slower"


def test_route_redirect_parser_to_parseragent():
    d = Diagnosis(
        decision="redirect_parser",
        root_cause="step 3 wrong",
        redirect_instruction="re-read the issue",
    )
    mentions, payload = route_diagnosis(d)
    assert mentions == ["ParserAgent"]
    assert payload.redirect == "re-read the issue"


# --- message formatting --------------------------------------------------

def test_format_confirm_message():
    d = Diagnosis(decision="confirm", root_cause="items[0] deref", redirect_instruction="")
    text = format_diagnosis_message("ReproAgent", d)
    assert text.startswith("@hanschundekad/reproagent")
    assert "items[0] deref" in text
    assert "Repro valid" in text


def test_format_redirect_parser_message():
    d = Diagnosis(
        decision="redirect_parser",
        root_cause="step 3 wrong",
        redirect_instruction="step 3 found no Add button, re-read the issue",
    )
    text = format_diagnosis_message("ParserAgent", d)
    assert text.startswith("@hanschundekad/parseragent")
    assert "re-read the issue" in text


# --- callback ------------------------------------------------------------

def test_callback_diagnoses_and_sends(monkeypatch):
    monkeypatch.setattr(
        agent_mod,
        "diagnose",
        lambda evidence, client, model=None: Diagnosis(
            decision="confirm", root_cause="items[0] deref", redirect_instruction=""
        ),
    )
    cb = make_diagnosis_callback(client=object(), repro_agent_id=REPRO_ID)
    a = FakeAgent()
    asyncio.run(cb(_payload(REPRO_ID), a))

    assert len(a.sent) == 1
    mentions, text = a.sent[0]
    assert mentions == ["ReproAgent"]
    assert "items[0] deref" in text
    # a thought event was logged (event, not message)
    assert any(etype == "thought" for _, etype in a.events)


def test_callback_redirects_to_parser(monkeypatch):
    monkeypatch.setattr(
        agent_mod,
        "diagnose",
        lambda evidence, client, model=None: Diagnosis(
            decision="redirect_parser",
            root_cause="step 3 wrong",
            redirect_instruction="re-read the issue",
        ),
    )
    cb = make_diagnosis_callback(client=object(), repro_agent_id=REPRO_ID)
    a = FakeAgent()
    asyncio.run(cb(_payload(REPRO_ID), a))

    mentions, text = a.sent[0]
    assert mentions == ["ParserAgent"]
    assert "re-read the issue" in text


def test_callback_ignores_non_reproagent(monkeypatch):
    called = False

    def _fail(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("diagnose must not run for non-ReproAgent senders")

    monkeypatch.setattr(agent_mod, "diagnose", _fail)
    cb = make_diagnosis_callback(client=object(), repro_agent_id=REPRO_ID)
    a = FakeAgent()
    asyncio.run(cb(_payload("some-other-agent-id"), a))

    assert a.sent == []
    assert called is False
