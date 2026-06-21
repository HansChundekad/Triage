# ReproAgent Echo (Phase 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable `ReproAgent` process that is a *pure echo* (no browser) — it joins the shared Band room, listens on its WebSocket, logs repro steps it receives from ParserAgent, and posts ONE hardcoded fake repro result @mentioning HypothesisAgent — proving three agents coordinate in one room with all three WebSockets alive at once.

**Architecture:** ReproAgent imports the Phase-2 `BandAgent` wrapper (never reimplements/modifies Band logic). Real, testable logic (building + formatting the fake result, the receive-and-respond handler) lives in `triage/repro_agent/echo.py` and is unit-tested with stubs. The Band WebSocket I/O is glue, proven live by a three-way smoke harness that mirrors Phase 2's `handshake.py`. NO Browserbase, NO Stagehand, NO real browser — that is Phase 4.

**Tech Stack:** Python 3.11+ (dev on 3.14), `asyncio`, `band-sdk 1.0.0` (only via the shared `BandAgent` wrapper), pytest.

## Global Constraints

- Work ONLY in the worktree `/Users/hanschundekad/triage-repro` (branch `phase3-repro`). Never edit the other worktrees.
- Always use the repo venv: `.venv/bin/pytest`, `.venv/bin/python`.
- Agent is named exactly `ReproAgent` — never a generic name.
- Every `send_message` call @mentions a target (≥1 mention). Directed talk = messages; logs = events. Never mix.
- Import `BandAgent` and payload types from `triage.shared.band`. DO NOT modify or reimplement the shared Band module. If it seems to need changing, STOP and tell the user.
- NO browser code of any kind (no Browserbase, no Stagehand). That is Phase 4.
- TDD for real logic: write the failing test first. Per-task commits with scoped messages. Never commit secrets (`.env` is gitignored).
- Don't over-build. The echo is a placeholder standing in for Phase-4 browser execution.

---

## File Structure

- `triage/repro_agent/echo.py` — **Create.** All ReproAgent echo logic: `build_fake_result()`, `format_result_message()`, `_sender_is_hypothesis()`, the async `handle_parser_message()` callback, and the `run()` entrypoint.
- `triage/repro_agent/__main__.py` — **Create.** Thin entrypoint so `python -m triage.repro_agent` runs the agent.
- `tests/test_repro_echo.py` — **Create.** Unit tests for the pure functions and the handler (driven by a fake agent + stub payload). No live network.
- `scripts/three_way_smoke.py` — **Create.** Throwaway verification harness: connects the real ReproAgent echo + a stub ParserAgent (canned sender) + a stub HypothesisAgent (prints receipts), drives one round trip, asserts HypothesisAgent received the echo. Proves the Phase-3 goal.

Consumed from Phase 2 (do not modify):
```python
from triage.shared.band import BandAgent, ReproResultPayload  # triage/shared/band.py
from triage.config import load_config                          # triage/config.py
```
`BandAgent` interface (proven in Phase 2):
- `BandAgent(name, agent_id, api_key, on_message=async_cb)` — `on_message` signature: `async def cb(payload, agent: BandAgent)`.
- `await agent.connect(room_id=str|None) -> str` (None creates+prints a room; starts the listener task).
- `await agent.add_participant(name: AgentName)` — must be called by the room owner before a peer subscribes.
- `await agent.send_message(mentions: list[AgentName], text: str)` — raises `ValueError` if `mentions` empty.
- `await agent.send_event(content: str, event_type: "thought"|"error"|"task", metadata=None)`.
- `await agent.disconnect()`.
- The listener already drops self-sent messages and messages from other rooms; Band's Agent API only delivers messages where ReproAgent is @mentioned. `payload` exposes `.sender_name`, `.content`, `.sender_id`, `.chat_room_id`.

`ReproResultPayload` (the evidence shape we must emit):
```python
ReproResultPayload(success: bool, evidence: list[str], console_errors: list[str], session_url: str = "")
```

---

### Task 1: Fake-result core (pure functions, TDD)

**Files:**
- Create: `triage/repro_agent/echo.py`
- Test: `tests/test_repro_echo.py`

**Interfaces:**
- Consumes: `ReproResultPayload` from `triage.shared.band`.
- Produces:
  - `build_fake_result() -> ReproResultPayload` — hardcoded placeholder result (bug reproduced).
  - `format_result_message(result: ReproResultPayload) -> str` — renders an @HypothesisAgent message string including the literal handle `@hanschundekad/hypothesisagent`.
  - `_sender_is_hypothesis(sender_name: str | None) -> bool` — guard so a HypothesisAgent reply never triggers another echo (no ping-pong).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_repro_echo.py
from triage.repro_agent.echo import (
    build_fake_result,
    format_result_message,
    _sender_is_hypothesis,
)
from triage.shared.band import ReproResultPayload


def test_build_fake_result_shape():
    result = build_fake_result()
    assert isinstance(result, ReproResultPayload)
    assert result.success is True              # placeholder: bug reproduced
    assert result.evidence                     # non-empty
    assert any("TypeError" in c for c in result.console_errors)
    assert "PLACEHOLDER" in result.session_url  # honest: not a real Browserbase session


def test_format_result_message_mentions_hypothesis():
    text = format_result_message(build_fake_result())
    assert "@hanschundekad/hypothesisagent" in text
    assert "TypeError" in text
    assert "BUG REPRODUCED" in text


def test_sender_is_hypothesis():
    assert _sender_is_hypothesis("hanschundekad/hypothesisagent") is True
    assert _sender_is_hypothesis("HypothesisAgent") is True
    assert _sender_is_hypothesis("hanschundekad/parseragent") is False
    assert _sender_is_hypothesis(None) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_repro_echo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'triage.repro_agent.echo'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# triage/repro_agent/echo.py
"""ReproAgent — Phase 3 echo (placeholder for Phase-4 browser execution).

NO browser here. This stands in for the real Browserbase/Stagehand work that
will live in this package in Phase 4. For now ReproAgent joins the shared Band
room, logs repro steps it receives from ParserAgent, and posts ONE hardcoded
fake repro result @mentioning HypothesisAgent — to prove three-way coordination.
"""
from __future__ import annotations

from triage.shared.band import ReproResultPayload

# Literal Band handle for the @mention target (matches triage/shared/band.py).
_HYPOTHESIS_HANDLE = "@hanschundekad/hypothesisagent"


def build_fake_result() -> ReproResultPayload:
    """Hardcoded placeholder result. Phase 4 replaces this with real browser evidence."""
    return ReproResultPayload(
        success=True,  # placeholder: we "reproduced" the reported bug
        evidence=[
            "Ran all 4 repro steps in PLACEHOLDER mode (no real browser yet — Phase 4).",
            "After deleting the last todo item, the app rendered a blank screen.",
        ],
        console_errors=[
            "TypeError: Cannot read properties of undefined (reading 'length') "
            "— empty array access after delete",
        ],
        session_url="https://www.browserbase.com/sessions/PLACEHOLDER-phase4-not-real-yet",
    )


def format_result_message(result: ReproResultPayload) -> str:
    """Render a directed @HypothesisAgent message from a ReproResultPayload."""
    verdict = "BUG REPRODUCED" if result.success else "BUG NOT REPRODUCED"
    lines = [
        f"{_HYPOTHESIS_HANDLE} repro result (Phase 3 echo — placeholder, no real browser):",
        f"verdict: {verdict}",
        "evidence:",
        *[f"  - {e}" for e in result.evidence],
        "console_errors:",
        *[f"  - {c}" for c in result.console_errors],
        f"session_url: {result.session_url}",
    ]
    return "\n".join(lines)


def _sender_is_hypothesis(sender_name: str | None) -> bool:
    """True if a message came from HypothesisAgent (so we don't echo its replies)."""
    return bool(sender_name and "hypothesis" in sender_name.lower())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_repro_echo.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add triage/repro_agent/echo.py tests/test_repro_echo.py
git commit -m "feat: ReproAgent fake-result core (Phase 3 echo)"
```

---

### Task 2: Receive-and-echo handler + runnable process (TDD for handler)

**Files:**
- Modify: `triage/repro_agent/echo.py` (append handler + `run()`)
- Create: `triage/repro_agent/__main__.py`
- Test: `tests/test_repro_echo.py` (append handler tests)

**Interfaces:**
- Consumes: `build_fake_result`, `format_result_message`, `_sender_is_hypothesis` (Task 1); `BandAgent`, `load_config`.
- Produces:
  - `async def handle_parser_message(payload, agent) -> None` — the `on_message` callback: logs the received steps, posts a `task` event (log), then sends ONE `@HypothesisAgent` message. Ignores messages whose sender is HypothesisAgent.
  - `async def run() -> None` — loads config, connects ReproAgent to `cfg.band_room_id`, best-effort adds HypothesisAgent as participant, stays alive indefinitely.

- [ ] **Step 1: Write the failing handler tests**

```python
# append to tests/test_repro_echo.py
import asyncio
from types import SimpleNamespace

from triage.repro_agent.echo import handle_parser_message


class _FakeAgent:
    name = "ReproAgent"

    def __init__(self):
        self.messages = []  # list[(mentions, text)]
        self.events = []    # list[(content, event_type)]

    async def send_message(self, mentions, text):
        self.messages.append((mentions, text))

    async def send_event(self, content, event_type, metadata=None):
        self.events.append((content, event_type))


def _msg(sender_name):
    return SimpleNamespace(
        sender_name=sender_name,
        sender_id="peer-id",
        chat_room_id="room-id",
        content="1. Open app  2. Add todo  3. Delete it  4. observe blank screen",
    )


def test_handler_sends_one_message_to_hypothesis():
    agent = _FakeAgent()
    asyncio.run(handle_parser_message(_msg("hanschundekad/parseragent"), agent))
    assert len(agent.messages) == 1
    mentions, text = agent.messages[0]
    assert mentions == ["HypothesisAgent"]
    assert "@hanschundekad/hypothesisagent" in text
    assert len(agent.events) == 1            # one log event posted
    assert agent.events[0][1] == "task"


def test_handler_ignores_hypothesis_sender():
    agent = _FakeAgent()
    asyncio.run(handle_parser_message(_msg("hanschundekad/hypothesisagent"), agent))
    assert agent.messages == []              # no echo of a Hypothesis reply
    assert agent.events == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_repro_echo.py -k handler -v`
Expected: FAIL with `ImportError: cannot import name 'handle_parser_message'`.

- [ ] **Step 3: Implement the handler + run()**

```python
# append to triage/repro_agent/echo.py
import asyncio
import logging

from triage.config import load_config
from triage.shared.band import BandAgent

logger = logging.getLogger(__name__)


async def handle_parser_message(payload, agent) -> None:
    """on_message callback: log received steps, then echo ONE fake result @HypothesisAgent."""
    sender = getattr(payload, "sender_name", None)
    print(f"\n[ReproAgent] << received from {sender}:")
    print(f"    {payload.content!r}")

    if _sender_is_hypothesis(sender):
        print("[ReproAgent] sender is HypothesisAgent — ignoring (Phase 3 echo has no retry logic).")
        return

    print("[ReproAgent] logging repro steps (placeholder — real browser execution is Phase 4):")
    print(f"    {payload.content}")

    # events = logs (mirrors what real per-step browser logging will look like in Phase 4)
    await agent.send_event(
        "Executed repro steps in PLACEHOLDER mode (Phase 3 echo — no real browser).",
        "task",
    )

    text = format_result_message(build_fake_result())
    print("[ReproAgent] >> sending fake repro result @HypothesisAgent:")
    print(text)
    await agent.send_message(["HypothesisAgent"], text)
    print("[ReproAgent] sent.\n")


async def run() -> None:
    """Connect ReproAgent to the shared room and stay alive on its WebSocket."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = load_config()
    agent = BandAgent(
        name="ReproAgent",
        agent_id=cfg.band_repro.agent_id,
        api_key=cfg.band_repro.api_key,
        on_message=handle_parser_message,
    )

    room_id = await agent.connect(room_id=cfg.band_room_id)
    print(f"[ReproAgent] connected to room {room_id}. Listening for @mentions. Ctrl-C to stop.")

    # Best-effort: make sure our echo target can actually receive it. ReproAgent
    # proved it can add participants in Phase 2. May no-op if already a member or
    # if ReproAgent does not own this room — log and continue either way.
    try:
        await agent.add_participant("HypothesisAgent")
        print("[ReproAgent] ensured HypothesisAgent is a room participant.")
    except Exception as exc:  # noqa: BLE001 — defensive, non-fatal
        print(f"[ReproAgent] could not add HypothesisAgent (may already be a member): {exc}")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await agent.disconnect()
        print("[ReproAgent] disconnected.")
```

- [ ] **Step 4: Create the module entrypoint**

```python
# triage/repro_agent/__main__.py
"""Run the ReproAgent echo process: python -m triage.repro_agent"""
import asyncio

from triage.repro_agent.echo import run

if __name__ == "__main__":
    asyncio.run(run())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_repro_echo.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add triage/repro_agent/echo.py triage/repro_agent/__main__.py tests/test_repro_echo.py
git commit -m "feat: ReproAgent echo handler + runnable process (Phase 3)"
```

---

### Task 3: Three-way smoke harness + live proof

**Files:**
- Create: `scripts/three_way_smoke.py`

**Interfaces:**
- Consumes: `BandAgent` from `triage.shared.band`; `handle_parser_message` from `triage.repro_agent.echo` (the REAL echo handler under test).
- Produces: a runnable script that exits 0 when HypothesisAgent receives ReproAgent's echo within the timeout, 1 otherwise.

- [ ] **Step 1: Write the harness**

```python
#!/usr/bin/env python
"""Phase 3 proof: ParserAgent → ReproAgent (echo) → HypothesisAgent, all three live.

Throwaway verification harness (mirrors Phase 2 scripts/handshake.py). The stub
ParserAgent/HypothesisAgent here are test doubles ONLY — the real ones are built
in their own worktrees and integrate on main. This drives the REAL ReproAgent
echo handler so the three-way @mention routing is proven from this worktree.

Run:
    cp /Users/hanschundekad/Triage/.env /Users/hanschundekad/triage-repro/.env  # if missing
    .venv/bin/python scripts/three_way_smoke.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from triage.repro_agent.echo import handle_parser_message
from triage.shared.band import BandAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

TIMEOUT = 30

_REQUIRED = (
    "BAND_PARSER_API_KEY", "BAND_PARSER_AGENT_ID",
    "BAND_REPRO_API_KEY", "BAND_REPRO_AGENT_ID",
    "BAND_HYPOTHESIS_API_KEY", "BAND_HYPOTHESIS_AGENT_ID",
)


async def main() -> int:
    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        print(f"[ERROR] Missing env vars: {', '.join(missing)}")
        print("        Copy /Users/hanschundekad/Triage/.env into this worktree.")
        return 1

    hypothesis_got = asyncio.Event()

    async def hypothesis_on_message(payload, agent: BandAgent) -> None:
        print(f"\n  [HypothesisAgent] << received from {payload.sender_name}:")
        print(f"      {payload.content!r}\n")
        hypothesis_got.set()

    repro = BandAgent(
        name="ReproAgent",
        agent_id=os.environ["BAND_REPRO_AGENT_ID"],
        api_key=os.environ["BAND_REPRO_API_KEY"],
        on_message=handle_parser_message,   # the REAL echo under test
    )
    parser = BandAgent(
        name="ParserAgent",
        agent_id=os.environ["BAND_PARSER_AGENT_ID"],
        api_key=os.environ["BAND_PARSER_API_KEY"],
    )
    hypothesis = BandAgent(
        name="HypothesisAgent",
        agent_id=os.environ["BAND_HYPOTHESIS_AGENT_ID"],
        api_key=os.environ["BAND_HYPOTHESIS_API_KEY"],
        on_message=hypothesis_on_message,
    )

    print("\n=== TRIAGE Phase 3 — Three-Way Band Coordination ===\n")

    # ReproAgent owns the room so it can admit both peers before they subscribe.
    print("[1/6] Connecting ReproAgent (creates room) ...")
    room_id = await repro.connect(room_id=None)
    print(f"[2/6] ReproAgent admitting ParserAgent + HypothesisAgent to {room_id} ...")
    await repro.add_participant("ParserAgent")
    await repro.add_participant("HypothesisAgent")

    print("[3/6] Connecting ParserAgent + HypothesisAgent ...")
    await parser.connect(room_id=room_id)
    await hypothesis.connect(room_id=room_id)
    await asyncio.sleep(1.5)  # let all three WebSockets stabilise

    print("[4/6] ParserAgent → @ReproAgent: repro steps ...")
    await parser.send_message(
        mentions=["ReproAgent"],
        text=(
            "@hanschundekad/reproagent repro steps for issue #1 — "
            "1. Open app  2. Add one todo  3. Delete it  4. observe screen"
        ),
    )

    print(f"[5/6] Waiting for HypothesisAgent to receive the echo (timeout {TIMEOUT}s) ...")
    try:
        await asyncio.wait_for(hypothesis_got.wait(), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        print("\n[FAIL] HypothesisAgent never received ReproAgent's echo.")
        await parser.disconnect(); await hypothesis.disconnect(); await repro.disconnect()
        return 1

    print("[6/6] === THREE-WAY COORDINATION COMPLETE ===")
    print(f"Room: {room_id}  — all three WebSockets alive, @mention routing works.\n")
    await parser.disconnect(); await hypothesis.disconnect(); await repro.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Ensure the worktree has credentials**

Run: `cp /Users/hanschundekad/Triage/.env /Users/hanschundekad/triage-repro/.env`
(`.env` is gitignored — never committed. Skip if it already exists.)

- [ ] **Step 3: Run the full test suite (no regressions)**

Run: `.venv/bin/pytest`
Expected: PASS — the 18 existing tests plus the 5 new echo tests = 23 passing.

- [ ] **Step 4: Run the live three-way proof**

Run: `.venv/bin/python scripts/three_way_smoke.py`
Expected: prints the ParserAgent send, the ReproAgent receive + logged steps + outgoing fake result, the HypothesisAgent receipt, then `THREE-WAY COORDINATION COMPLETE`; exits 0.

- [ ] **Step 5: Sanity-check the standalone process boots**

Run: `timeout 8 .venv/bin/python -m triage.repro_agent; test $? -eq 124 && echo "OK: stayed alive until timeout"`
Expected: connects, prints "Listening for @mentions", stays alive until the 8s timeout kills it (exit 124).

- [ ] **Step 6: Commit, then STOP and show the user**

```bash
git add scripts/three_way_smoke.py
git commit -m "feat: three-way Band coordination smoke proof (Phase 3)"
```
Then stop and show the user the live run output. Do not merge to main — reconciliation with the real ParserAgent/HypothesisAgent worktrees happens there.

---

## Notes / flags for the user

- **`BAND_ROOM_ID` is empty** in `.env`. The standalone process and the smoke harness both create a fresh room and print its ID. Wiring all three worktrees to ONE shared `BAND_ROOM_ID` is a main-reconciliation step, not part of this echo.
- **No shared-module changes.** Everything imports `BandAgent` / `ReproResultPayload` as-is. If the wrapper turns out inadequate, STOP and raise it — do not edit `triage/shared/band.py` in this worktree.
- **No browser anywhere.** The fake result is explicitly labelled PLACEHOLDER so it can never be mistaken for real Phase-4 evidence (`session_url` contains `PLACEHOLDER`).
```
