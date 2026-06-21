# Phase 5 — ParserAgent (real) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ParserAgent's hardcoded Band echo with real logic — fetch the live GitHub issue, use Claude to turn its vague prose into structured repro steps (inferring unstated preconditions), and post them @ReproAgent, with a redirect re-parse loop.

**Architecture:** Three focused modules under `triage/parser_agent/`: `github.py` (httpx issue fetch), `claude.py` (Sonnet structured-output step extraction), and `agent.py` (Band-callback orchestration + message formatting + redirect re-parse). `__main__.py` keeps its Band wiring and delegates to `agent.py`. The legacy `echo.py` is deleted. The cross-agent contract stays the shared `ReproStepsPayload(issue_url, steps: list[str])` — no new fields.

**Tech Stack:** Python 3.11+ (dev on 3.14), `anthropic` (AsyncAnthropic, structured outputs), `httpx` (AsyncClient), the shared `triage.shared.band` layer, `pytest`. Use the repo venv (`.venv/`).

## Global Constraints

- Agent names are exact: `ParserAgent` / `ReproAgent` / `HypothesisAgent` — never generic.
- Every cross-agent `send_message` must include ≥1 `@mention` (structured `mentions` arg). No @mention = no recipient.
- `send_message` = directed talk; `send_event` = logs. Never mix.
- Conform to the existing shared schema `ReproStepsPayload(issue_url: str, steps: list[str])`. Do NOT add fields. Do NOT modify `triage/shared/band.py`.
- All browser/Stagehand work stays in ReproAgent — ParserAgent does NO browser work (pure Claude reasoning + GitHub fetch + Band messaging).
- Parse model is exactly `claude-sonnet-4-6`.
- Arize tracing is OUT of scope for this phase (deferred).
- GitHub fetch is unauthenticated (public repo) — no new env var.
- TDD: write the failing test first. Per-task commits. Use `.venv/bin/pytest`.
- Config is loaded via `from triage.config import load_config`. Existing fields used: `cfg.anthropic_api_key`, `cfg.github_issue_url`, `cfg.band_parser`, `cfg.band_repro`, `cfg.band_hypothesis`, `cfg.band_room_id`.

---

### Task 1: GitHub issue-URL → API-URL conversion

**Files:**
- Create: `triage/parser_agent/github.py`
- Test: `tests/test_parser_github.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `issue_api_url(web_url: str) -> str` — converts a `https://github.com/{owner}/{repo}/issues/{n}` web URL to its `https://api.github.com/repos/{owner}/{repo}/issues/{n}` REST URL. Raises `ValueError` on a non-issue URL.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_parser_github.py
from __future__ import annotations

import pytest

from triage.parser_agent.github import issue_api_url


def test_issue_api_url_converts_web_url():
    assert (
        issue_api_url("https://github.com/octocat/hello-world/issues/42")
        == "https://api.github.com/repos/octocat/hello-world/issues/42"
    )


def test_issue_api_url_tolerates_trailing_whitespace_and_http():
    assert (
        issue_api_url("  http://github.com/o/r/issues/7  ")
        == "https://api.github.com/repos/o/r/issues/7"
    )


def test_issue_api_url_rejects_non_issue_url():
    with pytest.raises(ValueError):
        issue_api_url("https://github.com/octocat/hello-world/pull/42")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_parser_github.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'triage.parser_agent.github'`

- [ ] **Step 3: Write minimal implementation**

```python
# triage/parser_agent/github.py
"""ParserAgent GitHub integration — fetch a live issue via the REST API.

No browser, no auth: a plain public GET of the issue ParserAgent must parse.
"""
from __future__ import annotations

import re

# GitHub REST API version header. Live docs surfaced "2026-03-10"; the header is
# optional and GitHub defaults sensibly, so we pin the stable, widely-supported
# value. Bump only if a needed field requires a newer version.
_API_VERSION = "2022-11-28"

_ISSUE_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)$"
)


def issue_api_url(web_url: str) -> str:
    """Convert a GitHub issue web URL to its REST API URL.

    Raises:
        ValueError: if ``web_url`` is not a GitHub issue URL.
    """
    match = _ISSUE_URL_RE.match(web_url.strip())
    if not match:
        raise ValueError(f"Not a GitHub issue URL: {web_url!r}")
    owner = match.group("owner")
    repo = match.group("repo")
    number = match.group("number")
    return f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_parser_github.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add triage/parser_agent/github.py tests/test_parser_github.py
git commit -m "feat(parser): add issue_api_url GitHub URL converter"
```

---

### Task 2: Fetch the issue over HTTP

**Files:**
- Modify: `triage/parser_agent/github.py`
- Test: `tests/test_parser_github.py`

**Interfaces:**
- Consumes: `issue_api_url` (Task 1), `httpx.AsyncClient`.
- Produces:
  - `Issue` dataclass with fields `title: str`, `body: str`, `url: str`.
  - `async def fetch_issue(web_url: str, *, http_client: httpx.AsyncClient) -> Issue` — GETs the issue with the GitHub `Accept` + `X-GitHub-Api-Version` headers; raises `RuntimeError` on non-200; returns `Issue` with `title`/`body` from the JSON (empty string when null) and `url` set to the original `web_url`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_parser_github.py
import asyncio

import httpx

from triage.parser_agent.github import Issue, fetch_issue


def test_fetch_issue_extracts_title_and_body_and_sends_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["accept"] = request.headers.get("Accept")
        seen["version"] = request.headers.get("X-GitHub-Api-Version")
        return httpx.Response(
            200,
            json={"title": "App goes blank", "body": "when I delete my last task"},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        issue = asyncio.run(
            fetch_issue("https://github.com/o/r/issues/7", http_client=client)
        )
    finally:
        asyncio.run(client.aclose())

    assert isinstance(issue, Issue)
    assert issue.title == "App goes blank"
    assert "delete my last task" in issue.body
    assert issue.url == "https://github.com/o/r/issues/7"
    assert seen["path"] == "/repos/o/r/issues/7"
    assert seen["accept"] == "application/vnd.github+json"
    assert seen["version"] == "2022-11-28"


def test_fetch_issue_null_body_becomes_empty_string():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"title": "T", "body": None})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        issue = asyncio.run(
            fetch_issue("https://github.com/o/r/issues/1", http_client=client)
        )
    finally:
        asyncio.run(client.aclose())
    assert issue.body == ""


def test_fetch_issue_raises_on_non_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(
                fetch_issue("https://github.com/o/r/issues/9", http_client=client)
            )
    finally:
        asyncio.run(client.aclose())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_parser_github.py -v`
Expected: FAIL with `ImportError: cannot import name 'Issue'` (and `fetch_issue`)

- [ ] **Step 3: Write minimal implementation**

Add to `triage/parser_agent/github.py` (imports at top, code below `issue_api_url`):

```python
# add to the top imports of triage/parser_agent/github.py
from dataclasses import dataclass

import httpx
```

```python
# add to the bottom of triage/parser_agent/github.py
@dataclass
class Issue:
    """A fetched GitHub issue — the raw material ParserAgent hands to Claude."""

    title: str
    body: str
    url: str


async def fetch_issue(web_url: str, *, http_client: httpx.AsyncClient) -> Issue:
    """Fetch a single GitHub issue via the public REST API.

    Args:
        web_url: the issue's github.com web URL (from ``cfg.github_issue_url``).
        http_client: an ``httpx.AsyncClient`` (injected so it can be mocked).

    Raises:
        RuntimeError: if GitHub returns a non-200 status.
    """
    api_url = issue_api_url(web_url)
    response = await http_client.get(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _API_VERSION,
        },
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub issue fetch failed ({response.status_code}) for {api_url}: "
            f"{response.text[:200]}"
        )
    data = response.json()
    return Issue(
        title=data.get("title") or "",
        body=data.get("body") or "",
        url=web_url,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_parser_github.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add triage/parser_agent/github.py tests/test_parser_github.py
git commit -m "feat(parser): add Issue + fetch_issue (httpx public GET)"
```

---

### Task 3: Claude step extraction (the inference)

**Files:**
- Create: `triage/parser_agent/claude.py`
- Test: `tests/test_parser_claude.py`

**Interfaces:**
- Consumes: `Issue` (Task 2), `ReproStepsPayload` from `triage.shared.band`, an `AsyncAnthropic`-shaped client exposing `await client.messages.create(...)` returning an object whose `.content` is a list of blocks with `.type` / `.text`.
- Produces:
  - `build_user_prompt(issue: Issue, redirect: str | None = None) -> str`.
  - `async def extract_steps(issue: Issue, *, client, redirect: str | None = None) -> ReproStepsPayload` — calls `claude-sonnet-4-6` with adaptive thinking and a structured-output JSON schema constraining the response to `{"steps": [str, ...]}`, then returns `ReproStepsPayload(issue_url=issue.url, steps=[...])`. When `redirect` is set, its text is woven into the prompt so Claude produces revised steps.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_parser_claude.py
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from triage.parser_agent.claude import build_user_prompt, extract_steps
from triage.parser_agent.github import Issue
from triage.shared.band import ReproStepsPayload


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_parser_claude.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'triage.parser_agent.claude'`

- [ ] **Step 3: Write minimal implementation**

```python
# triage/parser_agent/claude.py
"""ParserAgent reasoning — turn a vague GitHub issue into structured repro steps.

The impressive part: Claude infers preconditions the user never stated (e.g.
"delete my last task" implies a task must first be added). Output is constrained
to a JSON schema so it drops straight into the shared ReproStepsPayload.
"""
from __future__ import annotations

import json

from triage.parser_agent.github import Issue
from triage.shared.band import ReproStepsPayload

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 4096

_SYSTEM = (
    "You are a senior QA engineer. You receive a bug report filed by a "
    "non-technical user about a web to-do application. The report is vague and "
    "casual. Turn it into a precise, ordered list of reproduction steps that a "
    "browser-automation agent can execute literally, one action at a time, "
    "against the live app.\n\n"
    "Rules:\n"
    "- Each step is a single concrete UI action: focusing a field, typing a "
    "value, or clicking one button. Never bundle two actions into one step.\n"
    "- Phrase each step as a direct imperative the automation agent can act on "
    "(e.g. \"Type 'Buy groceries' into the new-task text input\", \"Click the "
    "Add button\").\n"
    "- CRITICAL: infer and include any precondition the user did not state but "
    "that must hold for the bug to occur. If the user says the app breaks when "
    "they delete their last task, the app must first contain a task — so you "
    "must add the step(s) to create a task before deleting it. Put inferred "
    "preconditions first, in order.\n"
    "- Do not include verification or assertion steps, and do not add "
    "commentary. Emit only the actions needed to reach the bug.\n"
    "- Order steps so executing them top to bottom reproduces the bug."
)

# Structured-output schema — constrains the response to a clean list of strings
# matching the shared ReproStepsPayload.steps shape. No new fields.
_STEPS_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["steps"],
    "additionalProperties": False,
}


def build_user_prompt(issue: Issue, redirect: str | None = None) -> str:
    """Render the user-turn prompt from the issue (plus optional redirect)."""
    prompt = (
        f"GitHub issue title: {issue.title}\n\n"
        f"GitHub issue body:\n{issue.body}\n\n"
        "Produce the ordered reproduction steps."
    )
    if redirect:
        prompt += (
            "\n\nA previous attempt to reproduce these steps failed. Feedback "
            f"from the reproduction agent:\n{redirect}\n\n"
            "Re-read the issue and produce a revised, corrected set of steps "
            "that addresses this feedback."
        )
    return prompt


async def extract_steps(
    issue: Issue,
    *,
    client,
    redirect: str | None = None,
) -> ReproStepsPayload:
    """Call Claude to extract structured repro steps from the issue.

    Args:
        issue: the fetched GitHub issue.
        client: an AsyncAnthropic client (injected for testability).
        redirect: optional feedback from a failed repro, woven into the prompt.
    """
    response = await client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": _STEPS_SCHEMA}},
        messages=[{"role": "user", "content": build_user_prompt(issue, redirect)}],
    )
    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)
    return ReproStepsPayload(issue_url=issue.url, steps=list(data["steps"]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_parser_claude.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add triage/parser_agent/claude.py tests/test_parser_claude.py
git commit -m "feat(parser): add Claude structured step extraction with precondition inference"
```

---

### Task 4: Message formatting + sender mapping (`agent.py`)

**Files:**
- Create: `triage/parser_agent/agent.py`
- Test: `tests/test_parser_agent.py`

**Interfaces:**
- Consumes: `ReproStepsPayload` from `triage.shared.band`; `AgentName` from `triage.shared.band`.
- Produces:
  - `format_steps_message(payload: ReproStepsPayload) -> str` — renders the directed @ReproAgent message as a header line plus one numbered line per step. **Contract for ReproAgent's parser:** step lines match `^\s*\d+\.\s+(.*)$`.
  - `sender_agent_name(sender_id: str, cfg) -> AgentName | None` — maps a Band sender UUID to its agent name (duck-typed cfg: reads `band_parser`/`band_repro`/`band_hypothesis` `.agent_id`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_parser_agent.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_parser_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'triage.parser_agent.agent'`

- [ ] **Step 3: Write minimal implementation**

```python
# triage/parser_agent/agent.py
"""ParserAgent orchestration — Band callback glue, message formatting, redirect.

Pure helpers (formatting, sender mapping) plus the async orchestration that
fetches + parses + posts. No browser work lives here.
"""
from __future__ import annotations

import logging

from triage.shared.band import AgentName, ReproStepsPayload

logger = logging.getLogger(__name__)


def format_steps_message(payload: ReproStepsPayload) -> str:
    """Render the structured steps as the directed @ReproAgent message.

    Format (the contract ReproAgent's parser reads): a header line, then one
    numbered line per step matching ``^\\s*\\d+\\.\\s+(.*)$``.
    """
    lines = [f"@ReproAgent repro steps for {payload.issue_url}:"]
    for index, step in enumerate(payload.steps, start=1):
        lines.append(f"{index}. {step}")
    return "\n".join(lines)


def sender_agent_name(sender_id: str, cfg) -> AgentName | None:
    """Map a Band sender UUID to its agent name, or None if unknown.

    ``cfg`` is duck-typed: only ``band_parser``/``band_repro``/``band_hypothesis``
    ``.agent_id`` are read (so tests can pass a lightweight stub).
    """
    by_id: dict[str, AgentName] = {
        cfg.band_parser.agent_id: "ParserAgent",
        cfg.band_repro.agent_id: "ReproAgent",
        cfg.band_hypothesis.agent_id: "HypothesisAgent",
    }
    return by_id.get(sender_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_parser_agent.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add triage/parser_agent/agent.py tests/test_parser_agent.py
git commit -m "feat(parser): add agent.py with numbered-line message format + sender mapping"
```

---

### Task 5: Orchestration — initial post + redirect re-parse callback

**Files:**
- Modify: `triage/parser_agent/agent.py`
- Test: `tests/test_parser_agent.py`

**Interfaces:**
- Consumes: `fetch_issue`, `Issue` (Task 2); `extract_steps` (Task 3); `format_steps_message`, `sender_agent_name` (Task 4). A Band-agent object exposing `await agent.send_message(mentions: list[AgentName], text: str)`.
- Produces:
  - `async def post_initial_steps(cfg, *, anthropic_client, http_client, agent, issue_cache: dict) -> None` — fetches the issue (storing it in `issue_cache["issue"]`), extracts steps, posts `@ReproAgent`.
  - `def make_on_message(cfg, *, anthropic_client, http_client, issue_cache: dict)` → async `on_message(payload, agent)` callback. On a message whose sender maps to `ReproAgent`/`HypothesisAgent`, treats `payload.content` as a redirect, re-extracts steps (reusing the cached issue, fetching it if absent), and re-posts `@ReproAgent`. Ignores any other sender (self/unknown).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_parser_agent.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_parser_agent.py -v`
Expected: FAIL with `ImportError: cannot import name 'make_on_message'` (and `post_initial_steps`)

- [ ] **Step 3: Write minimal implementation**

Add imports to the top of `triage/parser_agent/agent.py`:

```python
from triage.parser_agent.claude import extract_steps
from triage.parser_agent.github import fetch_issue
```

Append to `triage/parser_agent/agent.py`:

```python
async def post_initial_steps(
    cfg,
    *,
    anthropic_client,
    http_client,
    agent,
    issue_cache: dict,
) -> None:
    """Fetch the configured issue, parse it, and post the steps @ReproAgent."""
    issue = await fetch_issue(cfg.github_issue_url, http_client=http_client)
    issue_cache["issue"] = issue
    payload = await extract_steps(issue, client=anthropic_client)
    text = format_steps_message(payload)
    logger.info("[ParserAgent] posting %d steps @ReproAgent", len(payload.steps))
    await agent.send_message(["ReproAgent"], text)


def make_on_message(cfg, *, anthropic_client, http_client, issue_cache: dict):
    """Build the async on_message callback for ParserAgent.

    Reacts only to redirects from ReproAgent / HypothesisAgent (a message that
    @mentions ParserAgent to route work back). Re-parses the issue with their
    feedback woven in, and re-posts revised steps @ReproAgent. Self-messages and
    unknown senders are ignored.
    """

    async def on_message(payload, agent) -> None:
        sender = sender_agent_name(payload.sender_id, cfg)
        if sender not in ("ReproAgent", "HypothesisAgent"):
            logger.info(
                "[ParserAgent] ignoring message from %s (not a redirect)", sender
            )
            return

        redirect = payload.content
        logger.info("[ParserAgent] redirect from %s — re-parsing", sender)

        if issue_cache.get("issue") is None:
            issue_cache["issue"] = await fetch_issue(
                cfg.github_issue_url, http_client=http_client
            )
        payload_out = await extract_steps(
            issue_cache["issue"], client=anthropic_client, redirect=redirect
        )
        await agent.send_message(["ReproAgent"], format_steps_message(payload_out))

    return on_message
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_parser_agent.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add triage/parser_agent/agent.py tests/test_parser_agent.py
git commit -m "feat(parser): add initial-post + redirect re-parse orchestration"
```

---

### Task 6: Wire `__main__.py` to real logic; delete the echo

**Files:**
- Modify: `triage/parser_agent/__main__.py`
- Delete: `triage/parser_agent/echo.py`
- Delete: `tests/test_parser_echo.py`

**Interfaces:**
- Consumes: `post_initial_steps`, `make_on_message` (Task 5); `BandAgent` from `triage.shared.band`; `load_config` from `triage.config`; `anthropic.AsyncAnthropic`; `httpx.AsyncClient`.
- Produces: a runnable `python -m triage.parser_agent` that connects as the ParserAgent Band identity, posts real parsed steps @ReproAgent on startup, and re-parses on redirects.

- [ ] **Step 1: Confirm `echo.py` has no remaining importers besides what this task removes**

Run: `grep -rn "parser_agent.echo\|parser_agent import echo\|from triage.parser_agent.echo" triage tests scripts`
Expected: matches only in `triage/parser_agent/__main__.py` and `tests/test_parser_echo.py` (both handled below). If anything else references it, update that import to `triage.parser_agent.agent` before deleting.

- [ ] **Step 2: Replace `triage/parser_agent/__main__.py`**

```python
#!/usr/bin/env python
"""Runnable ParserAgent (Phase 5 — real GitHub fetch + Claude parsing).

Connects to Band as the BAND_PARSER_* identity, joins the shared room
(BAND_ROOM_ID), fetches the live GitHub issue, uses Claude to extract structured
repro steps (inferring unstated preconditions), and posts them @ReproAgent.
Then listens — re-parsing and re-posting whenever ReproAgent/HypothesisAgent
routes work back with a redirect.

Run:
    source .venv/bin/activate
    python -m triage.parser_agent
"""
from __future__ import annotations

import asyncio
import logging
import sys

import anthropic
import httpx

from triage.config import load_config
from triage.parser_agent.agent import make_on_message, post_initial_steps
from triage.shared.band import BandAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

STARTUP_DELAY = 2.0  # let the WebSocket settle before the first post


async def main() -> int:
    cfg = load_config()

    anthropic_client = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)
    http_client = httpx.AsyncClient()
    issue_cache: dict = {"issue": None}

    agent = BandAgent(
        name="ParserAgent",
        agent_id=cfg.band_parser.agent_id,
        api_key=cfg.band_parser.api_key,
        on_message=make_on_message(
            cfg,
            anthropic_client=anthropic_client,
            http_client=http_client,
            issue_cache=issue_cache,
        ),
    )

    print("\n=== TRIAGE Phase 5 — ParserAgent (real) ===\n")

    room_id = await agent.connect(room_id=cfg.band_room_id)
    print(f"[ParserAgent] connected to room {room_id}")

    # Solo bootstrap convenience: if we just created the room (no BAND_ROOM_ID),
    # add the other two so the room is immediately usable by their worktrees.
    if cfg.band_room_id is None:
        await agent.add_participant("ReproAgent")
        await agent.add_participant("HypothesisAgent")
        print(
            f"[ParserAgent] created room {room_id} and added ReproAgent + "
            f"HypothesisAgent — set BAND_ROOM_ID={room_id} for the other worktrees"
        )

    # Event = log (no @mention). Message = directed talk (below).
    await agent.send_event("ParserAgent online (real parsing)", "task")

    await asyncio.sleep(STARTUP_DELAY)

    print(f"[ParserAgent] fetching + parsing issue: {cfg.github_issue_url}")
    await post_initial_steps(
        cfg,
        anthropic_client=anthropic_client,
        http_client=http_client,
        agent=agent,
        issue_cache=issue_cache,
    )
    print("[ParserAgent] posted steps @ReproAgent.")

    print("[ParserAgent] listening — Ctrl-C to exit ...\n")
    try:
        await asyncio.Event().wait()  # run indefinitely on the WebSocket
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await agent.disconnect()
        await http_client.aclose()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n[ParserAgent] interrupted — shutting down.")
        sys.exit(0)
```

- [ ] **Step 3: Delete the legacy echo module and its test**

```bash
git rm triage/parser_agent/echo.py tests/test_parser_echo.py
```

- [ ] **Step 4: Run the full suite to verify nothing regressed**

Run: `.venv/bin/pytest`
Expected: PASS — all tests green (the new `test_parser_github.py`, `test_parser_claude.py`, `test_parser_agent.py` pass; the deleted `test_parser_echo.py` is gone; the rest of the suite is unchanged).

- [ ] **Step 5: Verify `__main__` imports cleanly (no live connection)**

Run: `.venv/bin/python -c "import triage.parser_agent.__main__; print('import ok')"`
Expected: prints `import ok` with no ImportError.

- [ ] **Step 6: Commit**

```bash
git add triage/parser_agent/__main__.py
git commit -m "feat(parser): wire __main__ to real fetch+parse+post; delete echo stub"
```

---

## Self-Review

**1. Spec coverage**
- Fetch live GitHub issue via API → Task 1 (URL) + Task 2 (fetch). ✓
- Claude turns prose into structured steps, inferring unstated preconditions → Task 3 (system prompt explicitly demands precondition inference). ✓
- Output in existing shared schema, no new fields → Task 3 returns `ReproStepsPayload(issue_url, steps)`; schema constrains to `{"steps": [...]}`. ✓
- Post @ReproAgent via shared Band module, don't modify it → Tasks 4–6 use `agent.send_message(["ReproAgent"], ...)`; `band.py` untouched. ✓
- Redirect re-parse loop → Task 5 `make_on_message`. ✓
- Named exactly ParserAgent, every message @mentions, events vs messages → Task 6 uses `send_event` for logs, `send_message(["ReproAgent"], ...)` for talk. ✓
- Sonnet 4.6 parse model; no Arize; unauthenticated GitHub → Tasks 3, 2 (no new env var), no Arize task. ✓
- Don't over-build → 3 small modules, no extra config, YAGNI. ✓

**2. Placeholder scan:** No TBD/TODO/"add error handling" placeholders — every code step is complete. ✓

**3. Type consistency:** `Issue(title, body, url)`, `extract_steps(issue, *, client, redirect=None) -> ReproStepsPayload`, `fetch_issue(web_url, *, http_client) -> Issue`, `format_steps_message(payload) -> str`, `sender_agent_name(sender_id, cfg)`, `post_initial_steps(...issue_cache)`, `make_on_message(...issue_cache)` — names and signatures are identical across the tasks that define and consume them. ✓

**Open coordination note (not a gap in this plan):** ReproAgent's `handle_parser_message` currently ignores the incoming steps and runs hardcoded `_STEPS`. For the end-to-end Phase-5 flow, the ReproAgent worktree must parse the numbered-line block this plan emits (lines matching `^\s*\d+\.\s+(.*)$`) and pass those steps into `run_repro()`. That change lives in the ReproAgent worktree, not here — flagged for handoff.
