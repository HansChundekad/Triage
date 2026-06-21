from __future__ import annotations

import re
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


def test_format_steps_message_empty_steps_is_header_only():
    payload = ReproStepsPayload(
        issue_url="https://github.com/o/r/issues/7",
        steps=[],
    )
    msg = format_steps_message(payload)

    assert msg.startswith("@ReproAgent")
    assert "https://github.com/o/r/issues/7" in msg
    assert not any(re.match(r"^\s*\d+\.\s+", line) for line in msg.splitlines())


def test_sender_agent_name_maps_known_ids():
    cfg = _fake_cfg()
    assert sender_agent_name("repro-id", cfg) == "ReproAgent"
    assert sender_agent_name("hypothesis-id", cfg) == "HypothesisAgent"
    assert sender_agent_name("parser-id", cfg) == "ParserAgent"


def test_sender_agent_name_returns_none_for_unknown():
    assert sender_agent_name("nobody", _fake_cfg()) is None


import asyncio
import json

from triage.parser_agent.agent import make_on_message, post_initial_steps
from triage.parser_agent.github import Issue


class _FakeAgent:
    def __init__(self) -> None:
        self.name = "ParserAgent"
        self.sent: list[tuple[list[str], str]] = []

    async def send_message(self, mentions, text) -> None:
        self.sent.append((list(mentions), text))


class _FakeMessages:
    def __init__(self, steps: list[str]) -> None:
        self._text = json.dumps({"steps": steps})
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self._text)]
        )


class _FakeAnthropic:
    def __init__(self, steps: list[str]) -> None:
        self.messages = _FakeMessages(steps)


def _msg(sender_id: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(sender_id=sender_id, sender_name="x", content=content)


def _cached_issue() -> dict:
    return {
        "issue": Issue(
            title="T",
            body="B",
            url="https://github.com/o/r/issues/7",
        )
    }


def test_post_initial_steps_fetches_parses_and_posts(monkeypatch):
    cfg = _fake_cfg()
    cfg.github_issue_url = "https://github.com/o/r/issues/7"
    agent = _FakeAgent()
    anthropic_client = _FakeAnthropic(["Add a task", "Delete it"])
    issue_cache: dict = {"issue": None}

    async def fake_fetch(web_url, *, http_client):
        return Issue(title="T", body="B", url=web_url)

    monkeypatch.setattr("triage.parser_agent.agent.fetch_issue", fake_fetch)

    asyncio.run(
        post_initial_steps(
            cfg,
            anthropic_client=anthropic_client,
            http_client=object(),
            agent=agent,
            issue_cache=issue_cache,
        )
    )

    assert issue_cache["issue"] is not None
    assert len(agent.sent) == 1
    mentions, text = agent.sent[0]
    assert mentions == ["ReproAgent"]
    assert "1. Add a task" in text


def test_on_message_redirect_reparses_and_reposts():
    cfg = _fake_cfg()
    cfg.github_issue_url = "https://github.com/o/r/issues/7"
    agent = _FakeAgent()
    anthropic_client = _FakeAnthropic(["Revised step one"])
    issue_cache = _cached_issue()

    cb = make_on_message(
        cfg,
        anthropic_client=anthropic_client,
        http_client=object(),
        issue_cache=issue_cache,
    )
    asyncio.run(
        cb(_msg("repro-id", "@ParserAgent step 3 found no Add button"), agent)
    )

    # Re-parsed with the redirect woven into the prompt.
    user_content = anthropic_client.messages.calls[0]["messages"][0]["content"]
    assert "no Add button" in user_content
    # Re-posted @ReproAgent.
    assert len(agent.sent) == 1
    assert agent.sent[0][0] == ["ReproAgent"]
    assert "1. Revised step one" in agent.sent[0][1]


def test_on_message_ignores_self_and_unknown_senders():
    cfg = _fake_cfg()
    agent = _FakeAgent()
    anthropic_client = _FakeAnthropic(["x"])
    cb = make_on_message(
        cfg,
        anthropic_client=anthropic_client,
        http_client=object(),
        issue_cache=_cached_issue(),
    )

    asyncio.run(cb(_msg("parser-id", "my own message"), agent))
    asyncio.run(cb(_msg("stranger", "hello"), agent))

    assert agent.sent == []
    assert anthropic_client.messages.calls == []
