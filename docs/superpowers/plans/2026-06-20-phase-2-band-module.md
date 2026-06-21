# Phase 2: Shared Band Module + Two-Agent Handshake

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared `triage/shared/band.py` module every agent imports and prove it works with a live two-agent (ParserAgent + ReproAgent) WebSocket handshake in a real Band room.

**Architecture:** A thin `BandAgent` wrapper around `band.Agent` + `band.core.simple_adapter.SimpleAdapter` — one class, instantiated three ways via the namespaced env keys. The handshake script runs both agents concurrently with `asyncio.gather`, waits for the reply, then shuts both down cleanly.

**Tech Stack:** `band-sdk==1.0.0` (installed), `anthropic` (for `AnthropicAdapter`), `asyncio`, `python-dotenv`, `pydantic`.

## Global Constraints

- Agent names: `ParserAgent`, `ReproAgent`, `HypothesisAgent` — never generic.
- Every message must have ≥1 mention — enforced in the module, not caller.
- Messages = directed talk (`send_message`). Events = structured logs (`send_event`). Never mixed.
- Env namespace: `BAND_PARSER_*`, `BAND_REPRO_*`, `BAND_HYPOTHESIS_*`.
- `BAND_ROOM_ID` env var: use if set; create a new room if empty and print the ID.
- Python 3.11+, repo `.venv`, `band-sdk` adapter pattern (`SimpleAdapter`).
- No Anthropic API calls in Phase 2 — agents respond with hardcoded replies in the handshake. No LLM costs.
- **SDK drift found:** `AnthropicAdapter(api_key=...)` is deprecated — use `provider_key=` instead. Doc says `AnthropicAdapter` but the live SDK also accepts `SimpleAdapter` subclass directly (no LLM needed for Phase 2). Use `SimpleAdapter` for the handshake to keep it free of LLM calls.

---

## File Map

| Path | What it does |
|---|---|
| `triage/shared/band.py` | **Replace stub.** `BandAgent` class + `AgentName` enum + message schema dataclasses. |
| `triage/shared/__init__.py` | Re-export `BandAgent`, `AgentName`, schema types. |
| `triage/config.py` | Add `band_room_id: str \| None` field + `BAND_ROOM_ID` optional env var. |
| `.env` + `.env.example` | Add `BAND_ROOM_ID=` (optional). |
| `scripts/handshake.py` | **New.** Runnable two-agent handshake proof. Not imported by agents. |
| `tests/test_band_module.py` | Unit tests for the module interface (no live network). |

---

## Task 1: Extend config + env for BAND_ROOM_ID

**Files:**
- Modify: `triage/config.py`
- Modify: `.env`
- Modify: `.env.example`
- Test: `tests/test_config.py` (extend existing)

**Interfaces:**
- Produces: `Config.band_room_id: str | None` — `None` means "create a room at runtime"

- [ ] **Step 1: Write failing test**

```python
# tests/test_config.py — add at bottom

def test_band_room_id_optional(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.delenv("BAND_ROOM_ID", raising=False)
    cfg = load_config(load_env=False)
    assert cfg.band_room_id is None

def test_band_room_id_loaded_when_set(monkeypatch):
    _set_all(monkeypatch)
    monkeypatch.setenv("BAND_ROOM_ID", "some-room-uuid")
    cfg = load_config(load_env=False)
    assert cfg.band_room_id == "some-room-uuid"
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd /Users/hanschundekad/Triage && source .venv/bin/activate && pytest tests/test_config.py::test_band_room_id_optional -v
```
Expected: `AttributeError` or `TypeError` — `Config` has no `band_room_id`.

- [ ] **Step 3: Add field to Config + loader**

In `triage/config.py`, add to `Config` dataclass:
```python
band_room_id: str | None
```

In `load_config`, after the existing `band_hypothesis` line:
```python
band_room_id=env.get("BAND_ROOM_ID") or None,
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/test_config.py -v
```
Expected: all 8 tests PASS.

- [ ] **Step 5: Update .env.example and .env**

Add after the `BAND_HYPOTHESIS_AGENT_ID` block in both files:
```
# Optional. If empty, the handshake script creates a new room and prints its ID.
BAND_ROOM_ID=
```

- [ ] **Step 6: Fill .env with real credentials**

```
BAND_PARSER_API_KEY=band_a_1781995760_pIXe3uKRi6nKIqdkYSo0xM6rG9M-3GHr
BAND_PARSER_AGENT_ID=7b63179e-025d-4426-b403-6bd2da4d23d2
BAND_REPRO_API_KEY=band_a_1781995786_5uqQuAaL26W6QOZfa5hb7yS1nmp_JrUw
BAND_REPRO_AGENT_ID=40ceca32-dcc4-493d-991c-246101d3b1e0
BAND_HYPOTHESIS_API_KEY=band_a_1781995711_dTsu2cmHNpYWQGatvF6fKN9ppf0Ql8bM
BAND_HYPOTHESIS_AGENT_ID=1c92f15a-1ece-4d41-9af4-f476cf4dadd5
```
(Leave `BAND_ROOM_ID=` empty for first run — handshake will create one.)

- [ ] **Step 7: Commit**

```bash
git add triage/config.py tests/test_config.py .env.example
git commit -m "feat: add optional BAND_ROOM_ID to Config (Phase 2)"
```

---

## Task 2: Message schema dataclasses

**Files:**
- Modify: `triage/shared/band.py` (replace stub entirely)
- Test: `tests/test_band_module.py` (new file)

**Interfaces:**
- Produces:
  - `AgentName` — `Literal["ParserAgent", "ReproAgent", "HypothesisAgent"]`
  - `ReproStepsPayload(issue_url: str, steps: list[str])` — ParserAgent → ReproAgent
  - `ReproResultPayload(success: bool, evidence: list[str], console_errors: list[str], session_url: str)` — ReproAgent → HypothesisAgent
  - `HypothesisPayload(root_cause: str, redirect: str | None)` — HypothesisAgent → ReproAgent (redirect) or ParserAgent (done)

- [ ] **Step 1: Write failing schema tests**

```python
# tests/test_band_module.py
from triage.shared.band import ReproStepsPayload, ReproResultPayload, HypothesisPayload

def test_repro_steps_payload_round_trips():
    p = ReproStepsPayload(issue_url="https://github.com/x/y/issues/1", steps=["click X", "delete Y"])
    assert p.issue_url == "https://github.com/x/y/issues/1"
    assert p.steps == ["click X", "delete Y"]

def test_repro_result_payload_round_trips():
    p = ReproResultPayload(
        success=False,
        evidence=["blank screen"],
        console_errors=["TypeError: Cannot read properties of undefined"],
        session_url="https://www.browserbase.com/sessions/abc123",
    )
    assert p.success is False
    assert len(p.console_errors) == 1

def test_hypothesis_payload_no_redirect():
    p = HypothesisPayload(root_cause="null dereference on empty list", redirect=None)
    assert p.redirect is None

def test_hypothesis_payload_with_redirect():
    p = HypothesisPayload(root_cause="race condition", redirect="retry with slower delete")
    assert p.redirect == "retry with slower delete"
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_band_module.py -v
```
Expected: `ImportError` — `triage.shared.band` has no these names yet.

- [ ] **Step 3: Write the schema + module skeleton**

Replace `triage/shared/band.py` entirely:

```python
"""Shared Band coordination layer for ParserAgent, ReproAgent, HypothesisAgent."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal

from band import Agent
from band.core.simple_adapter import SimpleAdapter
from band.core.protocols import AgentToolsProtocol
from band.core.types import PlatformMessage

logger = logging.getLogger(__name__)

AgentName = Literal["ParserAgent", "ReproAgent", "HypothesisAgent"]

_AGENT_HANDLES: dict[AgentName, str] = {
    "ParserAgent": "@hanschundekad/parseragent",
    "ReproAgent": "@hanschundekad/reproagent",
    "HypothesisAgent": "@hanschundekad/hypothesisagent",
}


# --- Structured message payloads ---

@dataclass
class ReproStepsPayload:
    """ParserAgent → ReproAgent: structured repro steps from a GitHub issue."""
    issue_url: str
    steps: list[str] = field(default_factory=list)


@dataclass
class ReproResultPayload:
    """ReproAgent → HypothesisAgent: evidence from a repro attempt."""
    success: bool
    evidence: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    session_url: str = ""


@dataclass
class HypothesisPayload:
    """HypothesisAgent → ReproAgent (redirect) or ParserAgent (done)."""
    root_cause: str
    redirect: str | None = None


# --- BandAgent wrapper ---

class _MessageHandler(SimpleAdapter):
    """SimpleAdapter that calls a user-supplied async callback on every message."""

    def __init__(self, on_message_cb):
        super().__init__()
        self._cb = on_message_cb

    async def on_message(
        self,
        msg: PlatformMessage,
        tools: AgentToolsProtocol,
        history,
        participants_msg,
        contacts_msg,
        *,
        is_session_bootstrap: bool,
        room_id: str,
    ) -> None:
        await self._cb(msg, tools)


class BandAgent:
    """One Band agent identity. Three agents share this class, one each."""

    def __init__(
        self,
        name: AgentName,
        agent_id: str,
        api_key: str,
        on_message=None,
    ):
        self.name = name
        self.handle = _AGENT_HANDLES[name]
        self._agent_id = agent_id
        self._api_key = api_key
        self._on_message = on_message or (lambda msg, tools: asyncio.sleep(0))
        self._agent: Agent | None = None
        self._room_id: str | None = None

    async def connect(self, room_id: str | None = None) -> str:
        """Connect to Band and join/create a room. Returns the room_id."""
        handler = _MessageHandler(self._on_message)
        self._agent = Agent.create(
            adapter=handler,
            agent_id=self._agent_id,
            api_key=self._api_key,
        )
        await self._agent.start()
        logger.info("[%s] connected", self.name)

        if room_id:
            self._room_id = room_id
        else:
            # Create a new room and print the ID for reuse
            tools = await self._agent._runtime._get_or_create_tools(None)
            self._room_id = await tools.create_chatroom()
            print(f"[{self.name}] Created room: {self._room_id}  ← set BAND_ROOM_ID={self._room_id}")

        logger.info("[%s] using room %s", self.name, self._room_id)
        return self._room_id

    async def send_message(self, mentions: list[AgentName], text: str) -> None:
        """Send a directed message. Raises if mentions is empty."""
        if not mentions:
            raise ValueError("send_message requires at least one mention")
        if self._agent is None:
            raise RuntimeError("Call connect() first")
        tools = self._agent._runtime._get_bound_tools(self._room_id)
        handles = [_AGENT_HANDLES[m] for m in mentions]
        await tools.send_message(content=text, mentions=handles)
        logger.info("[%s] → %s: %s", self.name, mentions, text[:80])

    async def send_event(
        self,
        content: str,
        event_type: Literal["thought", "error", "task"],
        metadata: dict | None = None,
    ) -> None:
        """Post a structured event (tool call, thought, error, progress)."""
        if self._agent is None:
            raise RuntimeError("Call connect() first")
        tools = self._agent._runtime._get_bound_tools(self._room_id)
        await tools.send_event(content=content, message_type=event_type, metadata=metadata)

    async def disconnect(self) -> None:
        if self._agent:
            await self._agent.stop(timeout=5.0)
            self._agent = None
            logger.info("[%s] disconnected", self.name)
```

- [ ] **Step 4: Run schema tests**

```bash
pytest tests/test_band_module.py -v
```
Expected: 4 PASS.

- [ ] **Step 5: Update triage/shared/__init__.py**

```python
from .band import (
    AgentName,
    BandAgent,
    ReproStepsPayload,
    ReproResultPayload,
    HypothesisPayload,
)

__all__ = [
    "AgentName",
    "BandAgent",
    "ReproStepsPayload",
    "ReproResultPayload",
    "HypothesisPayload",
]
```

- [ ] **Step 6: Commit**

```bash
git add triage/shared/band.py triage/shared/__init__.py tests/test_band_module.py
git commit -m "feat: shared Band module — schema types + BandAgent wrapper (Phase 2)"
```

---

## Task 3: Two-agent handshake script

**Files:**
- Create: `scripts/handshake.py`

**Interfaces:**
- Consumes: `BandAgent`, `AgentName`, `load_config()` from Phase 1 + Tasks 1–2
- Produces: runnable script; exits 0 on success, 1 on timeout

- [ ] **Step 1: Create scripts/ directory and handshake.py**

```python
#!/usr/bin/env python
"""Phase 2 handshake proof: ParserAgent sends, ReproAgent replies.

Run:
    source .venv/bin/activate
    python scripts/handshake.py

Both agents connect via WebSocket. ParserAgent sends a message @mentioning
ReproAgent. ReproAgent's subscription fires; it replies @mentioning ParserAgent.
Script exits once the reply lands (or after 30s timeout).
"""
from __future__ import annotations

import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from triage.config import load_config
from triage.shared.band import BandAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)

TIMEOUT = 30  # seconds before we give up


async def main() -> int:
    cfg = load_config(load_env=False)  # already loaded above
    reply_received = asyncio.Event()

    # --- ReproAgent: listens, replies once ---
    async def repro_on_message(msg, tools):
        text = getattr(msg, "content", str(msg))
        print(f"\n  [ReproAgent] << received: {text!r}")
        print("  [ReproAgent] >> replying to ParserAgent ...")
        await tools.send_message(
            content="@hanschundekad/parseragent ACK — repro steps received, starting browser session.",
            mentions=["@hanschundekad/parseragent"],
        )
        reply_received.set()

    repro = BandAgent(
        name="ReproAgent",
        agent_id=cfg.band_repro.agent_id,
        api_key=cfg.band_repro.api_key,
        on_message=repro_on_message,
    )

    # --- ParserAgent: connects, sends once ---
    parser = BandAgent(
        name="ParserAgent",
        agent_id=cfg.band_parser.agent_id,
        api_key=cfg.band_parser.api_key,
    )

    room_id = cfg.band_room_id

    print("\n=== TRIAGE Phase 2 Handshake ===\n")

    # Connect both agents
    print("[1/4] Connecting ReproAgent ...")
    room_id = await repro.connect(room_id=room_id)

    print(f"[2/4] Connecting ParserAgent to room {room_id} ...")
    await parser.connect(room_id=room_id)

    # Give WebSockets a moment to stabilise
    await asyncio.sleep(1.0)

    print("[3/4] ParserAgent sending repro steps @mentioning ReproAgent ...")
    await parser.send_message(
        mentions=["ReproAgent"],
        text=(
            "@hanschundekad/reproagent Repro steps for issue #42: "
            "1. Open app  2. Add one todo item  3. Delete it  "
            "→ expected: empty state  actual: blank screen + TypeError"
        ),
    )

    print("[4/4] Waiting for ReproAgent reply (timeout 30s) ...\n")
    try:
        await asyncio.wait_for(reply_received.wait(), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        print("\n[FAIL] Timed out — no reply received from ReproAgent.")
        return 1

    print("\n=== HANDSHAKE COMPLETE ===")
    print("Both WebSockets stayed alive. Routing via @mention works.\n")

    await parser.disconnect()
    await repro.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Make executable**

```bash
chmod +x /Users/hanschundekad/Triage/scripts/handshake.py
```

- [ ] **Step 3: Dry-run import check (no network)**

```bash
cd /Users/hanschundekad/Triage && source .venv/bin/activate && python -c "import scripts.handshake" 2>&1 | head -5
```
Expected: either silent (imports ok) or a `load_config` error about missing env vars — NOT an `ImportError`.

- [ ] **Step 4: Run the live handshake**

```bash
cd /Users/hanschundekad/Triage && source .venv/bin/activate && python scripts/handshake.py
```

Expected output (approximately):
```
=== TRIAGE Phase 2 Handshake ===

[1/4] Connecting ReproAgent ...
[2/4] Connecting ParserAgent to room <room-id> ...
[3/4] ParserAgent sending repro steps @mentioning ReproAgent ...
[4/4] Waiting for ReproAgent reply (timeout 30s) ...

  [ReproAgent] << received: '@hanschundekad/reproagent Repro steps ...'
  [ReproAgent] >> replying to ParserAgent ...

=== HANDSHAKE COMPLETE ===
Both WebSockets stayed alive. Routing via @mention works.
```

If `BAND_ROOM_ID` was empty, note the printed room ID and set it in `.env`.

- [ ] **Step 5: Commit**

```bash
git add scripts/handshake.py
git commit -m "feat: two-agent Band handshake proof script (Phase 2)"
```

---

## SDK Drift Notes

| Doc says | Live SDK (`band-sdk==1.0.0`) | Impact |
|---|---|---|
| `AnthropicAdapter(api_key=...)` | `api_key` deprecated — use `provider_key=` | Use `SimpleAdapter` in Phase 2 (no LLM calls needed) |
| `agent.run()` runs forever | `agent.start()` + `agent.stop(timeout)` cleanly separate | Use start/stop pattern for scripts |
| Doc shows `Agent.create(adapter=..., agent_id=..., api_key=...)` | Confirmed — exact match | No drift |
| `send_message(mentions, text)` | `send_message(content, mentions)` — arg order differs | Use kwargs always |

---

## Self-Review

- **BAND_ROOM_ID create path:** Task 1 adds the env var; Task 3 uses it with fallback to room creation. ✅
- **Three agent identities:** Config already has them; BandAgent takes `AgentName` enum. ✅
- **@mention enforcement:** `send_message` raises `ValueError` if `mentions` is empty. ✅
- **Messages vs events:** `send_message` for directed talk, `send_event` for logs — two separate methods. ✅
- **WebSocket stays alive:** `Agent.start()` opens it; `Agent.stop()` closes it. Handshake waits for reply before closing. ✅
- **Schema defined now:** `ReproStepsPayload`, `ReproResultPayload`, `HypothesisPayload` — Phase 3 agents import these. ✅
- **No LLM calls in Phase 2:** `SimpleAdapter` handles messages with a direct callback, no Anthropic API needed. ✅
