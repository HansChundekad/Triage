# Phase 5 — HypothesisAgent (real Claude reasoning) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace HypothesisAgent's hardcoded Band echo with real Claude reasoning that diagnoses root cause from ReproAgent's evidence and routes a confirm-or-redirect decision to the correct agent.

**Architecture:** A new pure-reasoning module (`reasoning.py`) calls Claude (`claude-sonnet-4-6`) with the evidence text and gets back a structured `Diagnosis` (decision + root cause + redirect instruction) via structured outputs. The existing Band-wired `agent.py` keeps all its connection/listener plumbing untouched and only swaps the echo callback for one that runs the reasoning (off the event loop via a worker thread), then maps the `Diagnosis` to a Band `@mention` and message. Confirm → @ReproAgent; redirect-repro → @ReproAgent; redirect-parser → @ParserAgent. No browser. The shared Band module is **not** modified — redirect routing is decided in the agent layer.

**Tech Stack:** Python 3.11+ (dev 3.14), `anthropic` SDK 0.111.0 (installed, verified), existing `triage.shared.band.BandAgent`, `triage.config`, `pytest`.

## Global Constraints

- Agent names are exact: `ParserAgent` / `ReproAgent` / `HypothesisAgent` — never generic.
- Every cross-agent `send_message` must include ≥1 `@mention`.
- `send_message` = directed talk; `send_event` = logs. Never mix.
- Do **not** modify, reimplement, or import privates from `triage/shared/band.py`. Conform to its existing `HypothesisPayload(root_cause, redirect)` schema.
- All-Python; use the repo venv `.venv/` for every command.
- TDD: write the failing test first. Per-task scoped commits. Never commit secrets.
- Model: `claude-sonnet-4-6` (decided — matches ReproAgent/ParserAgent). Anthropic SDK call shape verified against the `claude-api` skill: use `output_config={"format": {"type": "json_schema", "schema": ...}}` (the installed 0.111.0 SDK exposes `output_config`; the legacy `output_format` param does not exist). `budget_tokens` is removed on 4.x — use `thinking={"type": "adaptive"}`.
- Arize tracing is **out of scope** for this worktree (spec references TRIAGE_INTEGRATIONS §1 & §3 only). If Arize `auto_instrument` is wired globally later, the plain `client.messages.create` call here is captured automatically — no manual span needed now.

---

### Task 1: Reasoning module — Claude diagnosis from evidence

Pure reasoning. No Band, no asyncio. Takes the evidence text ReproAgent posts and returns a structured `Diagnosis`. The client is injected so tests never hit the network.

**Files:**
- Create: `triage/hypothesis_agent/reasoning.py`
- Test: `tests/test_hypothesis_reasoning.py`

**Interfaces:**
- Consumes: an `anthropic.Anthropic`-shaped client (only `.messages.create(...)` is used).
- Produces:
  - `Diagnosis` dataclass: `decision: Literal["confirm", "redirect_repro", "redirect_parser"]`, `root_cause: str`, `redirect_instruction: str`.
  - `diagnose(evidence_text: str, client, model: str = "claude-sonnet-4-6") -> Diagnosis`
  - Module constants `MODEL: str`, `SYSTEM_PROMPT: str`, `RESPONSE_SCHEMA: dict`.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_hypothesis_reasoning.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'triage.hypothesis_agent.reasoning'`

- [ ] **Step 3: Write the reasoning module**

```python
# triage/hypothesis_agent/reasoning.py
"""HypothesisAgent reasoning — Claude diagnoses root cause from evidence.

Pure reasoning: given the evidence text ReproAgent posts (verdict, session URL,
step evidence, console errors), call Claude and return a structured Diagnosis.
No Band, no asyncio — the Anthropic client is injected so this stays testable
and the caller controls its lifecycle.

SDK shape verified against the claude-api skill + installed anthropic 0.111.0:
structured output via output_config.format (json_schema); adaptive thinking
(budget_tokens is removed on Claude 4.x).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

MODEL = "claude-sonnet-4-6"

Decision = Literal["confirm", "redirect_repro", "redirect_parser"]


@dataclass
class Diagnosis:
    """Structured result of reasoning over one repro attempt's evidence."""

    decision: Decision
    root_cause: str
    redirect_instruction: str  # "" when decision == "confirm"


SYSTEM_PROMPT = (
    "You are HypothesisAgent in the TRIAGE bug-reproduction system. ReproAgent "
    "drove a REAL browser through a live app to reproduce a reported bug and has "
    "sent you the evidence from one attempt: a verdict, a session replay URL, "
    "step-by-step evidence, and any captured console errors.\n\n"
    "Reason about the likely ROOT CAUSE from the observed behavior and the "
    "console error ALONE — you cannot see the source code, and a diagnosis "
    "grounded in behavior is exactly what is wanted. Be specific and mechanistic "
    '(e.g. "reads items[0] after the array is emptied by the delete, '
    'dereferencing undefined").\n\n'
    "Then choose EXACTLY ONE decision:\n"
    '- "confirm": the evidence clearly shows the reported bug fired (e.g. blank '
    "screen plus a matching console TypeError). The repro is valid.\n"
    '- "redirect_repro": the repro looks wrong, incomplete, or did NOT actually '
    "trigger the bug (no crash, no matching error, or an action clearly failed "
    "mid-run). ReproAgent should retry with a concrete tweak — put it in "
    'redirect_instruction (e.g. "retry with a slower delete so the confirmation '
    'dialog registers").\n'
    '- "redirect_parser": the evidence shows the repro STEPS themselves were '
    "wrong — a step could not find its target element, or a precondition was "
    "missing — so the issue should be re-parsed. Put the concrete fix in "
    'redirect_instruction (e.g. "step 3 found no Add button — re-read the issue '
    'for the correct control name").\n\n'
    'For "confirm", set redirect_instruction to an empty string. Respond only '
    "via the structured schema."
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["confirm", "redirect_repro", "redirect_parser"],
        },
        "root_cause": {"type": "string"},
        "redirect_instruction": {"type": "string"},
    },
    "required": ["decision", "root_cause", "redirect_instruction"],
    "additionalProperties": False,
}


def diagnose(evidence_text: str, client, model: str = MODEL) -> Diagnosis:
    """Reason about root cause and confirm/redirect from one attempt's evidence.

    Args:
        evidence_text: the raw Band message content ReproAgent sent.
        client: an anthropic.Anthropic-shaped client (only messages.create used).
        model: Claude model id.

    Returns:
        A Diagnosis. Blocking/synchronous — call via asyncio.to_thread from
        async code so the WebSocket event loop is not stalled.
    """
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": evidence_text}],
        output_config={"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}},
    )
    text = next(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    )
    data = json.loads(text)
    return Diagnosis(
        decision=data["decision"],
        root_cause=data["root_cause"],
        redirect_instruction=data.get("redirect_instruction", ""),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_hypothesis_reasoning.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add triage/hypothesis_agent/reasoning.py tests/test_hypothesis_reasoning.py
git commit -m "feat(hypothesis): Claude reasoning module — diagnose() from evidence

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Wire reasoning into the Band callback + routing

Replace the echo callback with one that runs `diagnose()` (off the event loop) and posts a real diagnosis, routing the redirect to the right agent. Keep all BandAgent plumbing.

**Files:**
- Modify: `triage/hypothesis_agent/agent.py` (full rewrite of the echo logic; keep the `run()` connect/listen shape)
- Modify: `triage/hypothesis_agent/__init__.py:1-4`
- Test: `tests/test_hypothesis_agent.py` (replace the echo tests)

**Interfaces:**
- Consumes: `Diagnosis`, `diagnose`, `MODEL` from `triage.hypothesis_agent.reasoning` (Task 1); `BandAgent`, `HypothesisPayload`, `AgentName` from `triage.shared.band`; `Config`, `load_config` from `triage.config`.
- Produces:
  - `route_diagnosis(d: Diagnosis) -> tuple[list[AgentName], HypothesisPayload]`
  - `format_diagnosis_message(target: AgentName, d: Diagnosis) -> str`
  - `make_diagnosis_callback(client, repro_agent_id: str, model: str = MODEL) -> Callable`
  - `async run(cfg: Config | None = None) -> None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hypothesis_agent.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_hypothesis_agent.py -v`
Expected: FAIL — `ImportError: cannot import name 'route_diagnosis'` (the module still has only echo symbols)

- [ ] **Step 3: Rewrite `triage/hypothesis_agent/agent.py`**

```python
# triage/hypothesis_agent/agent.py
"""HypothesisAgent — Phase 5: real Claude reasoning.

When @mentioned by ReproAgent with evidence (verdict, session URL, step
evidence, console errors), reason about root cause with Claude and either:
  - confirm the repro (@ReproAgent), or
  - redirect ReproAgent to retry with a tweak (@ReproAgent), or
  - redirect ParserAgent to re-parse the issue (@ParserAgent).

Band wiring (connect / listener / disconnect) is reused unchanged from
triage.shared.band — nothing here reimplements or modifies it. The redirect
TARGET is decided in this layer; the shared HypothesisPayload(root_cause,
redirect) schema is conformed to as-is.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine

import anthropic

from triage.config import Config, load_config
from triage.hypothesis_agent.reasoning import MODEL, Diagnosis, diagnose
from triage.shared.band import AgentName, BandAgent, HypothesisPayload

logger = logging.getLogger(__name__)

# Cosmetic transcript handles (structured @mention routing is supplied
# separately via BandAgent.send_message(mentions=[...]); these mirror the
# Phase 2/3 convention for a readable room transcript).
_HANDLES: dict[AgentName, str] = {
    "ReproAgent": "@hanschundekad/reproagent",
    "ParserAgent": "@hanschundekad/parseragent",
}


def route_diagnosis(d: Diagnosis) -> tuple[list[AgentName], HypothesisPayload]:
    """Map a Diagnosis to (Band @mention targets, shared HypothesisPayload).

    confirm        → @ReproAgent, redirect=None
    redirect_repro → @ReproAgent, redirect=instruction
    redirect_parser→ @ParserAgent, redirect=instruction
    """
    if d.decision == "redirect_parser":
        target: AgentName = "ParserAgent"
    else:
        target = "ReproAgent"

    redirect = None if d.decision == "confirm" else (d.redirect_instruction or None)
    payload = HypothesisPayload(root_cause=d.root_cause, redirect=redirect)
    return [target], payload


def format_diagnosis_message(target: AgentName, d: Diagnosis) -> str:
    """Render the directed message text for the chosen target."""
    handle = _HANDLES[target]
    if d.decision == "confirm":
        return (
            f"{handle} confirmed, matches the report. "
            f"Root cause: {d.root_cause}. Repro valid."
        )
    return f"{handle} {d.redirect_instruction} (suspected cause: {d.root_cause})"


def make_diagnosis_callback(
    client,
    repro_agent_id: str,
    model: str = MODEL,
) -> Callable[[object, BandAgent], Coroutine]:
    """Build the on_message callback.

    Reacts only to messages from ReproAgent (by sender_id). Runs the blocking
    Claude diagnosis in a worker thread so the WebSocket loop is not stalled,
    then posts the diagnosis as a directed @mention. Everything is printed so
    @mention routing is watchable in the demo.
    """

    async def on_message(payload, agent: BandAgent) -> None:
        print(
            f"\n  [{agent.name}] << received from "
            f"{getattr(payload, 'sender_name', None)} "
            f"({getattr(payload, 'sender_id', None)}):"
        )
        print(f"      {payload.content!r}")

        if getattr(payload, "sender_id", None) != repro_agent_id:
            print(f"  [{agent.name}] (ignoring — sender is not ReproAgent)\n")
            return

        await agent.send_event("Diagnosing repro evidence with Claude", "thought")

        try:
            diagnosis = await asyncio.to_thread(diagnose, payload.content, client, model)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] diagnosis failed: %s", agent.name, exc)
            await agent.send_event(f"Diagnosis error: {exc}", "error")
            # Fail safe: ask ReproAgent to retry rather than going silent.
            await agent.send_message(
                ["ReproAgent"],
                f"{_HANDLES['ReproAgent']} diagnosis failed ({exc}); please retry.",
            )
            return

        mentions, _hyp_payload = route_diagnosis(diagnosis)
        text = format_diagnosis_message(mentions[0], diagnosis)
        await agent.send_event(
            f"Diagnosis: {diagnosis.decision} — {diagnosis.root_cause[:80]}", "thought"
        )
        await agent.send_message(mentions, text)
        print(f"  [{agent.name}] >> sent to {mentions}: {text!r}\n")

    return on_message


async def run(cfg: Config | None = None) -> None:
    """Connect HypothesisAgent to the shared room and listen indefinitely.

    Precondition: HypothesisAgent must already be a participant in
    cfg.band_room_id (the room creator / ReproAgent adds it). HypothesisAgent
    best-effort adds ParserAgent so the redirect_parser path can reach it.
    """
    cfg = cfg or load_config()
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    agent = BandAgent(
        name="HypothesisAgent",
        agent_id=cfg.band_hypothesis.agent_id,
        api_key=cfg.band_hypothesis.api_key,
        on_message=make_diagnosis_callback(client, cfg.band_repro.agent_id),
    )
    room_id = await agent.connect(room_id=cfg.band_room_id)

    try:
        await agent.add_participant("ParserAgent")
        print("[HypothesisAgent] ensured ParserAgent is a room participant.")
    except Exception as exc:  # noqa: BLE001
        print(f"[HypothesisAgent] could not add ParserAgent (may already be a member): {exc}")

    print(
        f"[HypothesisAgent] listening in room {room_id} — "
        "waiting for ReproAgent @mentions. Ctrl-C to stop."
    )
    try:
        await asyncio.Event().wait()  # stay alive forever
    finally:
        await agent.disconnect()
```

- [ ] **Step 4: Update the package exports**

Replace the whole of `triage/hypothesis_agent/__init__.py` with:

```python
"""HypothesisAgent package — Phase 5 real Claude reasoning."""
from .agent import (
    format_diagnosis_message,
    make_diagnosis_callback,
    route_diagnosis,
    run,
)
from .reasoning import Diagnosis, diagnose

__all__ = [
    "run",
    "make_diagnosis_callback",
    "route_diagnosis",
    "format_diagnosis_message",
    "Diagnosis",
    "diagnose",
]
```

- [ ] **Step 5: Run the HypothesisAgent tests**

Run: `.venv/bin/pytest tests/test_hypothesis_agent.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: Commit**

```bash
git add triage/hypothesis_agent/agent.py triage/hypothesis_agent/__init__.py tests/test_hypothesis_agent.py
git commit -m "feat(hypothesis): real Claude diagnosis + redirect routing in Band callback

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Update the live demo script + full-suite green

The Phase 3 echo demo imports the now-removed `make_echo_callback`. Update it to drive the real diagnosis callback, then confirm the entire suite passes.

**Files:**
- Modify: `scripts/hypothesis_echo_demo.py` (rename intent to Phase 5; build the diagnosis callback with a real client; send realistic evidence)

**Interfaces:**
- Consumes: `make_diagnosis_callback` from `triage.hypothesis_agent.agent`; `anthropic` for the client.

- [ ] **Step 1: Update the demo imports and callback wiring**

In `scripts/hypothesis_echo_demo.py`, replace the import line:

```python
from triage.hypothesis_agent.agent import make_echo_callback
```

with:

```python
import anthropic

from triage.hypothesis_agent.agent import make_diagnosis_callback
```

- [ ] **Step 2: Build the HypothesisAgent with a real client**

Replace the `hypo = BandAgent(...)` construction (currently using `make_echo_callback`) with:

```python
    hypo_client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    hypo = BandAgent(
        name="HypothesisAgent",
        agent_id=cfg.band_hypothesis.agent_id,
        api_key=cfg.band_hypothesis.api_key,
        on_message=make_diagnosis_callback(hypo_client, cfg.band_repro.agent_id),
    )
```

- [ ] **Step 3: Make the evidence realistic (matches ReproAgent's format)**

Replace the `repro.send_message(...)` evidence `text=` block with ReproAgent's real result shape so Claude diagnoses honest evidence:

```python
        text=(
            "@hanschundekad/hypothesisagent repro result:\n"
            "verdict: BUG REPRODUCED\n"
            "session_url: https://www.browserbase.com/sessions/demo\n"
            "evidence:\n"
            "  - focus input, type task, click add, click delete, confirm delete\n"
            "  - after confirming delete the app went blank (body text 8 chars)\n"
            "console_errors:\n"
            "  - TypeError: Cannot read properties of undefined (reading '0')"
        ),
```

- [ ] **Step 4: Update the demo's header docstring**

Change the module docstring's first line from the Phase 3 echo description to:

```python
"""Phase 5 live proof: ReproAgent stand-in ↔ HypothesisAgent real Claude diagnosis.
```

(Leave the rest of the docstring; the flow is unchanged — two WebSockets, @mention routing both directions. The stand-in now receives a real diagnosis instead of a placeholder.)

- [ ] **Step 5: Byte-compile the demo to catch syntax/import errors (no network)**

Run: `.venv/bin/python -m py_compile scripts/hypothesis_echo_demo.py`
Expected: no output (exit 0)

- [ ] **Step 6: Run the full test suite**

Run: `.venv/bin/pytest`
Expected: PASS — all prior tests plus the new reasoning (4) and agent (7) tests. No reference to `make_echo_callback` / `PLACEHOLDER_HYPOTHESIS` remains (grep confirms):

Run: `grep -rn "make_echo_callback\|PLACEHOLDER_HYPOTHESIS" triage/ tests/ scripts/`
Expected: no matches.

- [ ] **Step 7: Commit**

```bash
git add scripts/hypothesis_echo_demo.py
git commit -m "chore(hypothesis): update live demo to real Claude diagnosis callback

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4 (optional, manual): Live end-to-end smoke

Not a code change — a manual verification gate. Requires real Band + Anthropic credentials in `.env` and a shared `BAND_ROOM_ID`.

- [ ] **Step 1: Run the live demo**

Run: `.venv/bin/python scripts/hypothesis_echo_demo.py`
Expected: HypothesisAgent receives the evidence, prints a real Claude diagnosis, posts `@hanschundekad/reproagent confirmed ... Repro valid.`, the ReproAgent stand-in receives it, and the script prints `=== ECHO LOOP COMPLETE ===` and exits 0.

- [ ] **Step 2 (optional): Probe a redirect path**

Temporarily change the demo evidence `verdict:` to `BUG NOT REPRODUCED` with no console error, re-run, and confirm HypothesisAgent redirects (`redirect_repro` → `@hanschundekad/reproagent ... retry ...`) rather than confirming. Revert the change afterward.

---

## Self-Review

**1. Spec coverage**
- "Use Claude to reason about root cause from behavior + console error alone" → Task 1 `diagnose()` + `SYSTEM_PROMPT`.
- "Produce a structured root-cause hypothesis" → `Diagnosis` + structured outputs (Task 1).
- "Post diagnosis back @mentioning ReproAgent, in the shared hypothesis schema" → Task 2 `route_diagnosis` (builds `HypothesisPayload`) + `format_diagnosis_message` + callback `send_message` (confirm path).
- "Redirect on failure: @ReproAgent retry tweak OR @ParserAgent re-parse" → Task 2 `route_diagnosis` (`redirect_repro` → ReproAgent, `redirect_parser` → ParserAgent) + callback.
- "Wire confirm vs redirect, route to right agent" → Task 1 decision enum + Task 2 routing.
- "Keep Band wiring intact; replace only the echo" → Task 2 keeps `run()` connect/listener/disconnect; only the callback changes.
- "Named exactly HypothesisAgent; every message @mentions; events for logs, messages for talk" → callback uses `send_event` for thoughts/errors and `send_message(mentions=[...])` for the diagnosis; names exact via `AgentName`.
- "Conform to shared schemas; don't modify shared band module" → `HypothesisPayload` used as-is; redirect target decided in agent layer (no schema change).
- "Verify SDK vs live docs; flag drift" → Global Constraints note + verified `output_config` exists / `output_format` removed in 0.111.0.
- "No browser" → no Stagehand/Browserbase anywhere in this plan.

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to Task N". All code blocks are complete and self-contained.

**3. Type consistency:** `Diagnosis(decision, root_cause, redirect_instruction)` defined in Task 1 and consumed identically in Task 2. `route_diagnosis` returns `tuple[list[AgentName], HypothesisPayload]` and is tested/consumed consistently. `make_diagnosis_callback(client, repro_agent_id, model)` signature matches its test usage and `run()` call site. `diagnose(evidence_text, client, model)` signature matches Task 1 tests, the `asyncio.to_thread` call, and the monkeypatched stub (`lambda evidence, client, model=None`). Module-level `diagnose` is imported into `agent.py`'s namespace so the test's `monkeypatch.setattr(agent_mod, "diagnose", ...)` takes effect.
