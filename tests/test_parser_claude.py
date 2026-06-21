# tests/test_parser_claude.py
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from triage.parser_agent.claude import _SYSTEM, build_user_prompt, extract_steps
from triage.parser_agent.github import Issue
from triage.shared.band import ReproStepsPayload


def test_system_prompt_assumes_empty_start_no_navigation_confirm_delete():
    """A: the prompt must (1) assume the app starts empty so delete-bugs add a
    task first, (2) forbid navigation/open-app steps, (3) confirm deletions."""
    s = _SYSTEM.lower()
    assert "empty" in s                       # app starts with no tasks
    assert "navigat" in s                      # navigation steps are addressed (forbidden)
    assert "confirm" in s                      # deletions must be confirmed
    assert "sample" in s                       # explicitly ignore the issue's "sample todos"


class _FakeMessages:
    """Captures create() kwargs and returns a canned structured response."""

    def __init__(self, steps: list[str]) -> None:
        self._text = json.dumps({"steps": steps})
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        # Mimic a thinking-enabled response: a thinking block then the text block.
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", thinking="..."),
                SimpleNamespace(type="text", text=self._text),
            ]
        )


class _FakeClient:
    def __init__(self, steps: list[str]) -> None:
        self.messages = _FakeMessages(steps)


def _issue() -> Issue:
    return Issue(
        title="App goes blank",
        body="The app goes blank when I delete my last task.",
        url="https://github.com/o/r/issues/7",
    )


def test_extract_steps_returns_payload_with_steps():
    client = _FakeClient(["Add a task", "Delete the task"])
    payload = asyncio.run(extract_steps(_issue(), client=client))

    assert isinstance(payload, ReproStepsPayload)
    assert payload.issue_url == "https://github.com/o/r/issues/7"
    assert payload.steps == ["Add a task", "Delete the task"]


def test_extract_steps_uses_sonnet_and_structured_output():
    client = _FakeClient(["x"])
    asyncio.run(extract_steps(_issue(), client=client))

    kwargs = client.messages.calls[0]
    assert kwargs["model"] == "claude-sonnet-4-6"
    assert kwargs["output_config"]["format"]["type"] == "json_schema"


def test_extract_steps_threads_redirect_into_prompt():
    client = _FakeClient(["x"])
    asyncio.run(
        extract_steps(
            _issue(),
            client=client,
            redirect="@ParserAgent step 3 found no Add button, re-read the issue",
        )
    )
    user_content = client.messages.calls[0]["messages"][0]["content"]
    assert "no Add button" in user_content


def test_build_user_prompt_includes_title_and_body():
    prompt = build_user_prompt(_issue())
    assert "App goes blank" in prompt
    assert "delete my last task" in prompt
