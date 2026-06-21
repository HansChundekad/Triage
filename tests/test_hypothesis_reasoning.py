# tests/test_hypothesis_reasoning.py
"""Unit tests for HypothesisAgent reasoning (no live network)."""
import json
from types import SimpleNamespace

import pytest

from triage.hypothesis_agent.reasoning import Diagnosis, diagnose, MODEL


class FakeClient:
    """Stand-in for anthropic.Anthropic — records the create() kwargs and
    returns a canned response whose single text block holds `payload_json`."""

    def __init__(self, payload: dict):
        self._payload = payload
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        text_block = SimpleNamespace(type="text", text=json.dumps(self._payload))
        return SimpleNamespace(content=[text_block])


def test_diagnose_parses_confirm():
    client = FakeClient(
        {
            "decision": "confirm",
            "root_cause": "reads items[0] after the array empties",
            "redirect_instruction": "",
        }
    )
    d = diagnose("verdict: BUG REPRODUCED ...", client)
    assert isinstance(d, Diagnosis)
    assert d.decision == "confirm"
    assert "items[0]" in d.root_cause
    assert d.redirect_instruction == ""


def test_diagnose_parses_redirect_repro():
    client = FakeClient(
        {
            "decision": "redirect_repro",
            "root_cause": "delete never fired — no crash captured",
            "redirect_instruction": "retry with a slower delete",
        }
    )
    d = diagnose("verdict: BUG NOT REPRODUCED ...", client)
    assert d.decision == "redirect_repro"
    assert d.redirect_instruction == "retry with a slower delete"


def test_diagnose_sends_model_and_structured_output():
    client = FakeClient(
        {"decision": "confirm", "root_cause": "x", "redirect_instruction": ""}
    )
    diagnose("evidence", client)
    kwargs = client.calls[0]
    assert kwargs["model"] == MODEL
    # structured output requested via output_config.format (json_schema)
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    # evidence is the user turn
    assert kwargs["messages"][0]["role"] == "user"
    assert kwargs["messages"][0]["content"] == "evidence"
    # system prompt present
    assert isinstance(kwargs["system"], str) and kwargs["system"]


def test_diagnose_ignores_non_text_blocks():
    client = FakeClient(
        {"decision": "confirm", "root_cause": "ok", "redirect_instruction": ""}
    )

    # prepend a thinking-style block; diagnose must pick the text block
    def create(**kwargs):
        client.calls.append(kwargs)
        thinking = SimpleNamespace(type="thinking", thinking="...")
        text = SimpleNamespace(
            type="text",
            text=json.dumps(
                {"decision": "confirm", "root_cause": "ok", "redirect_instruction": ""}
            ),
        )
        return SimpleNamespace(content=[thinking, text])

    client.messages = SimpleNamespace(create=create)
    d = diagnose("evidence", client)
    assert d.root_cause == "ok"


def test_diagnose_raises_when_no_text_block():
    client = FakeClient({"decision": "confirm", "root_cause": "x", "redirect_instruction": ""})

    def create(**kwargs):
        client.calls.append(kwargs)
        thinking = SimpleNamespace(type="thinking", thinking="...")
        return SimpleNamespace(content=[thinking])

    client.messages = SimpleNamespace(create=create)
    with pytest.raises(ValueError, match="No text block"):
        diagnose("evidence", client)


def test_diagnose_parses_redirect_parser():
    client = FakeClient(
        {
            "decision": "redirect_parser",
            "root_cause": "step 3 found no Add button",
            "redirect_instruction": "re-read the issue for the correct control name",
        }
    )
    d = diagnose("verdict: BUG NOT REPRODUCED ...", client)
    assert d.decision == "redirect_parser"
    assert "re-read the issue" in d.redirect_instruction
