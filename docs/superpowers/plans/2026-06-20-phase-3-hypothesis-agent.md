# Phase 3 — HypothesisAgent (echo-only) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable `HypothesisAgent` process that connects to the shared Band room, listens on its WebSocket indefinitely, and — when ReproAgent @mentions it — logs the evidence and posts ONE hardcoded placeholder diagnosis back @mentioning ReproAgent. No Claude reasoning (that's Phase 5).

**Architecture:** All Band logic is reused from the Phase 2 shared module (`triage.shared.band.BandAgent` + `HypothesisPayload`) — **not reimplemented**. A new `triage/hypothesis_agent/` package holds the echo callback + lifecycle (`run()`), a `__main__` entrypoint (`python -m triage.hypothesis_agent`), and unit tests. A throwaway `scripts/hypothesis_echo_demo.py` (mirroring Phase 2's `handshake.py`) stands up a ReproAgent stand-in + the real HypothesisAgent in one process to prove the echo loop live with two WebSockets and @mention routing.

**Tech Stack:** `band-sdk==1.0.0` (via the shared `BandAgent` wrapper only), `asyncio`, `python-dotenv`, `pytest`. Python 3.11+ on the worktree `.venv`.

## Global Constraints

- Agent name is exactly `HypothesisAgent` — never generic. (`TRIAGE_INTEGRATIONS.md §7.4`)
- Every cross-agent message has ≥1 @mention. The shared `BandAgent.send_message` enforces this (raises `ValueError` on empty mentions).
- Messages = directed @mention talk; events = logs. This phase only sends **messages**. Don't mix.
- Three distinct Band identities; HypothesisAgent uses `BAND_HYPOTHESIS_*` only (`cfg.band_hypothesis`).
- **Import the shared Band module — do NOT reimplement Band logic and do NOT modify `triage/shared/band.py`.** If it seems to need changing, STOP and raise it with the user (reconcile on main, not in the worktree).
- No Claude/Anthropic calls — the diagnosis is a hardcoded placeholder standing in for Phase 5.
- No browser/Stagehand code (that lives only in ReproAgent).
- Per-task commits with scoped messages. Never commit secrets (`.env` is gitignored).

## SDK / doc drift already confirmed (flagged, no action needed)

- `TRIAGE_INTEGRATIONS.md §3.5` shows the Band connection as `Agent.create(adapter=SimpleAdapter())`. The **shipped** `triage/shared/band.py` instead uses `band.platform.link.BandLink` + REST clients, and was live-proven in Phase 2. Since we use `BandAgent` exclusively, this drift is fully absorbed by the wrapper — we never touch the raw SDK.
- Verified live in the installed SDK: the `on_message` callback signature is `async def cb(payload, agent: BandAgent)`, where `payload` is `band.platform.event.MessageCreatedPayload` (pydantic) exposing `.content`, `.sender_id`, `.sender_name`, `.chat_room_id`. (The Phase 2 *plan draft* showed an older `(msg, tools)` shape — superseded by the shipped code.)
- Band drift from Phase 2 (relevant to the demo): an agent cannot subscribe to a room until it is already a participant. The room creator must `add_participant(name)` for each other agent **before** that agent connects.

---

## File Map

| Path | What it does |
|---|---|
| `triage/hypothesis_agent/agent.py` | **New.** Echo callback (`make_echo_callback`), placeholder `HypothesisPayload`, message formatter, and `run()` lifecycle (connect + listen forever). |
| `triage/hypothesis_agent/__main__.py` | **New.** `python -m triage.hypothesis_agent` entrypoint: configure logging, `asyncio.run(run())`. |
| `triage/hypothesis_agent/__init__.py` | **Replace empty stub.** Re-export `run`, `make_echo_callback`, `PLACEHOLDER_HYPOTHESIS`. |
| `tests/test_hypothesis_agent.py` | **New.** Unit tests for the echo callback (fake agent + fake payload, no network). |
| `scripts/hypothesis_echo_demo.py` | **New.** Throwaway live 2-agent proof: ReproAgent stand-in → HypothesisAgent echo → back to ReproAgent. |

No config var is added, so `.env.example` / `triage/config.py` are untouched (`BAND_HYPOTHESIS_*` and `BAND_ROOM_ID` already exist). `docs/STATUS.md` is intentionally **not** edited here — it's a shared handoff file; reconcile Phase 3 status on main to avoid cross-worktree conflicts.

---

## Task 1: HypothesisAgent echo callback + unit tests

**Files:**
- Create: `triage/hypothesis_agent/agent.py`
- Modify: `triage/hypothesis_agent/__init__.py` (currently empty)
- Test: `tests/test_hypothesis_agent.py`

**Interfaces:**
- Consumes: `BandAgent`, `HypothesisPayload` from `triage.shared.band`; `Config`, `load_config` from `triage.config`.
- Produces:
  - `PLACEHOLDER_HYPOTHESIS: HypothesisPayload` — the hardcoded stand-in diagnosis.
  - `make_echo_callback(repro_agent_id: str) -> Callable[[payload, BandAgent], Coroutine]` — builds the `on_message` callback; echoes the placeholder to ReproAgent only when the message sender is ReproAgent.
  - `run(cfg: Config | None = None) -> None` — connect HypothesisAgent + listen forever (used by `__main__` in Task 2).

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_hypothesis_agent.py`:

```python
"""Unit tests for the HypothesisAgent echo callback (no live network)."""
import asyncio
from types import SimpleNamespace

from triage.hypothesis_agent.agent import make_echo_callback, PLACEHOLDER_HYPOTHESIS

REPRO_ID = "repro-agent-id-123"


class FakeAgent:
    """Stand-in for BandAgent that records send_message calls."""

    name = "HypothesisAgent"

    def __init__(self):
        self.sent: list[tuple[list[str], str]] = []

    async def send_message(self, mentions, text):
        self.sent.append((mentions, text))


def _payload(sender_id, content="ran all 4 steps — blank screen + TypeError"):
    return SimpleNamespace(
        sender_id=sender_id,
        sender_name="ReproAgent",
        content=content,
    )


def test_echoes_placeholder_back_to_reproagent():
    cb = make_echo_callback(REPRO_ID)
    agent = FakeAgent()
    asyncio.run(cb(_payload(REPRO_ID), agent))

    assert len(agent.sent) == 1
    mentions, text = agent.sent[0]
    assert mentions == ["ReproAgent"]
    assert PLACEHOLDER_HYPOTHESIS.root_cause in text
    assert "Repro valid" in text


def test_ignores_messages_not_from_reproagent():
    cb = make_echo_callback(REPRO_ID)
    agent = FakeAgent()
    asyncio.run(cb(_payload("some-other-agent-id"), agent))

    assert agent.sent == []


def test_placeholder_has_no_redirect():
    # Phase 3 echo just acknowledges; the redirect capability arrives later.
    assert PLACEHOLDER_HYPOTHESIS.redirect is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_hypothesis_agent.py -v`
Expected: FAIL with `ModuleNotFoundError`/`ImportError` — `triage.hypothesis_agent.agent` doesn't exist yet.

- [ ] **Step 3: Write the echo module**

Create `triage/hypothesis_agent/agent.py`:

```python
"""HypothesisAgent — Phase 3 echo-only.

Connects to the shared Band room as the HypothesisAgent identity, listens on
its WebSocket, and on a message @mentioning it from ReproAgent posts ONE
hardcoded placeholder diagnosis back @mentioning ReproAgent.

NO real Claude reasoning yet — the placeholder stands in for the real
root-cause analysis arriving in Phase 5. All Band logic is reused from
triage.shared.band; nothing here reimplements or modifies it.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine

from triage.config import Config, load_config
from triage.shared.band import BandAgent, HypothesisPayload

logger = logging.getLogger(__name__)

# Hardcoded stand-in for the Phase 5 Claude diagnosis. The fixed root cause
# matches TRIAGE's planted bug (blank screen + TypeError after deleting the
# last item). redirect=None means "no retry needed" — a plain acknowledgment.
PLACEHOLDER_HYPOTHESIS = HypothesisPayload(
    root_cause="reading items[0] after delete (empty-array dereference)",
    redirect=None,
)


def _format_hypothesis(h: HypothesisPayload) -> str:
    """Render a HypothesisPayload as the message text sent to ReproAgent.

    The structured mention (routing) is supplied separately via
    BandAgent.send_message(mentions=["ReproAgent"], ...); the leading handle
    here is for a readable room transcript, matching the Phase 2 convention.
    """
    text = (
        "@hanschundekad/reproagent confirmed, matches the report. "
        f"Root cause: {h.root_cause}. Repro valid."
    )
    if h.redirect:
        text += f" Redirect: {h.redirect}"
    return text


def make_echo_callback(
    repro_agent_id: str,
) -> Callable[[object, BandAgent], Coroutine]:
    """Build the on_message callback.

    Echoes PLACEHOLDER_HYPOTHESIS back to ReproAgent, but only for messages
    actually sent by ReproAgent (identified by sender_id). Everything sent and
    received is printed so @mention routing is watchable.
    """

    async def on_message(payload, agent: BandAgent) -> None:
        print(f"\n  [{agent.name}] << received from {payload.sender_name} ({payload.sender_id}):")
        print(f"      {payload.content!r}")

        if payload.sender_id != repro_agent_id:
            print(f"  [{agent.name}] (ignoring — sender is not ReproAgent)\n")
            return

        # Evidence logged. In Phase 5, real Claude reasoning replaces the line below.
        print(f"  [{agent.name}] evidence logged — posting placeholder diagnosis (Phase 5 reasons here).")
        text = _format_hypothesis(PLACEHOLDER_HYPOTHESIS)
        await agent.send_message(mentions=["ReproAgent"], text=text)
        print(f"  [{agent.name}] >> sent to ReproAgent: {text!r}\n")

    return on_message


async def run(cfg: Config | None = None) -> None:
    """Connect HypothesisAgent to the shared room and listen indefinitely.

    Precondition: HypothesisAgent must already be a participant in
    cfg.band_room_id (the room creator adds it — see scripts/hypothesis_echo_demo.py
    or, in the full system, ReproAgent/the orchestrator).
    """
    cfg = cfg or load_config()
    agent = BandAgent(
        name="HypothesisAgent",
        agent_id=cfg.band_hypothesis.agent_id,
        api_key=cfg.band_hypothesis.api_key,
        on_message=make_echo_callback(cfg.band_repro.agent_id),
    )
    room_id = await agent.connect(room_id=cfg.band_room_id)
    print(
        f"[HypothesisAgent] listening in room {room_id} — "
        "waiting for ReproAgent @mentions. Ctrl-C to stop."
    )
    try:
        await asyncio.Event().wait()  # stay alive forever
    finally:
        await agent.disconnect()
```

- [ ] **Step 4: Replace the empty `__init__.py`**

Replace `triage/hypothesis_agent/__init__.py` contents with:

```python
"""HypothesisAgent package — Phase 3 echo-only."""
from .agent import PLACEHOLDER_HYPOTHESIS, make_echo_callback, run

__all__ = ["run", "make_echo_callback", "PLACEHOLDER_HYPOTHESIS"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_hypothesis_agent.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `.venv/bin/pytest -q`
Expected: 21 passed (18 prior + 3 new).

- [ ] **Step 7: Commit**

```bash
git add triage/hypothesis_agent/agent.py triage/hypothesis_agent/__init__.py tests/test_hypothesis_agent.py
git commit -m "feat: HypothesisAgent echo callback + run() lifecycle (Phase 3)"
```

---

## Task 2: Standalone process entrypoint

**Files:**
- Create: `triage/hypothesis_agent/__main__.py`

**Interfaces:**
- Consumes: `run` from `triage.hypothesis_agent.agent` (Task 1).
- Produces: a runnable process — `python -m triage.hypothesis_agent`.

- [ ] **Step 1: Write the entrypoint**

Create `triage/hypothesis_agent/__main__.py`:

```python
"""Run the HypothesisAgent as a long-lived process.

    .venv/bin/python -m triage.hypothesis_agent

Connects to the shared Band room (BAND_ROOM_ID) as the HypothesisAgent
identity and listens forever, echoing a placeholder diagnosis whenever
ReproAgent @mentions it. Ctrl-C to stop.
"""
from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv

load_dotenv()

from triage.hypothesis_agent.agent import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[HypothesisAgent] stopped.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dry-run import check (no network)**

Run: `.venv/bin/python -c "import triage.hypothesis_agent.__main__"`
Expected: silent (imports OK). NOT an `ImportError`.

> A full `python -m triage.hypothesis_agent` run blocks forever waiting on Band;
> it is exercised end-to-end by the live demo in Task 3, so don't run it bare here.

- [ ] **Step 3: Commit**

```bash
git add triage/hypothesis_agent/__main__.py
git commit -m "feat: python -m triage.hypothesis_agent entrypoint (Phase 3)"
```

---

## Task 3: Live 2-agent echo demo + run

**Files:**
- Create: `scripts/hypothesis_echo_demo.py`

**Interfaces:**
- Consumes: `BandAgent` from `triage.shared.band`; `make_echo_callback` from `triage.hypothesis_agent.agent`; `load_config()`.
- Produces: runnable script; exits 0 when the echo lands, 1 on timeout.

- [ ] **Step 1: Write the demo script**

Create `scripts/hypothesis_echo_demo.py`:

```python
#!/usr/bin/env python
"""Phase 3 live proof: ReproAgent stand-in ↔ HypothesisAgent echo.

Run:
    .venv/bin/python scripts/hypothesis_echo_demo.py

A ReproAgent stand-in (no browser — just sends one evidence message) and the
REAL HypothesisAgent echo callback both connect to the shared Band room. The
stand-in @mentions HypothesisAgent with evidence; HypothesisAgent logs it and
posts its placeholder diagnosis back @mentioning ReproAgent; the stand-in
receives that echo and the script exits. Two live WebSockets, @mention routing
both directions.

If BAND_ROOM_ID is unset, a new room is created and its ID printed — copy it
into .env to reuse it (and so all three agents share ONE room).
"""
from __future__ import annotations

import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

from triage.config import load_config
from triage.shared.band import BandAgent
from triage.hypothesis_agent.agent import make_echo_callback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

TIMEOUT = 30  # seconds before giving up


async def main() -> int:
    cfg = load_config()
    echo_received: asyncio.Event = asyncio.Event()

    # ReproAgent stand-in: sends evidence, then listens for the echo back.
    async def repro_on_message(payload, agent: BandAgent) -> None:
        if payload.sender_id != cfg.band_hypothesis.agent_id:
            return  # only react to HypothesisAgent's echo
        print(f"\n  [{agent.name} stand-in] << echo from {payload.sender_name}:")
        print(f"      {payload.content!r}")
        echo_received.set()

    repro = BandAgent(
        name="ReproAgent",
        agent_id=cfg.band_repro.agent_id,
        api_key=cfg.band_repro.api_key,
        on_message=repro_on_message,
    )
    hypo = BandAgent(
        name="HypothesisAgent",
        agent_id=cfg.band_hypothesis.agent_id,
        api_key=cfg.band_hypothesis.api_key,
        on_message=make_echo_callback(cfg.band_repro.agent_id),
    )

    print("\n=== TRIAGE Phase 3 — HypothesisAgent Echo Demo ===\n")

    # ReproAgent stand-in creates/joins the room and must add HypothesisAgent
    # as a participant BEFORE HypothesisAgent subscribes (Band requires it).
    print("[1/5] Connecting ReproAgent stand-in ...")
    room_id = await repro.connect(room_id=cfg.band_room_id)

    print(f"[2/5] Adding HypothesisAgent to room {room_id} ...")
    await repro.add_participant("HypothesisAgent")

    print(f"[3/5] Connecting HypothesisAgent to room {room_id} ...")
    await hypo.connect(room_id=room_id)

    await asyncio.sleep(1.5)  # let both WebSockets stabilise

    print("[4/5] ReproAgent → @HypothesisAgent: sending evidence ...")
    await repro.send_message(
        mentions=["HypothesisAgent"],
        text=(
            "@hanschundekad/hypothesisagent ran all 4 steps — app went blank, "
            "console threw TypeError on empty array. Evidence + screenshots attached."
        ),
    )

    print(f"[5/5] Waiting for HypothesisAgent echo (timeout {TIMEOUT}s) ...")
    try:
        await asyncio.wait_for(echo_received.wait(), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        print("\n[FAIL] Timed out — no echo from HypothesisAgent.")
        print("       Check Band credentials and room membership.")
        await hypo.disconnect()
        await repro.disconnect()
        return 1

    print("=== ECHO LOOP COMPLETE ===")
    print(f"Room: {room_id}")
    print("Two WebSockets stayed alive. @mention routing works both directions.\n")

    await hypo.disconnect()
    await repro.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/hypothesis_echo_demo.py
```

- [ ] **Step 3: Dry-run import check (no network)**

Run: `.venv/bin/python -c "import scripts.hypothesis_echo_demo"`
Expected: silent, or a `load_config` error about missing env — NOT an `ImportError`.

- [ ] **Step 4: Run the live demo**

Run: `.venv/bin/python scripts/hypothesis_echo_demo.py`

Expected output (approximately):
```
=== TRIAGE Phase 3 — HypothesisAgent Echo Demo ===

[1/5] Connecting ReproAgent stand-in ...
[2/5] Adding HypothesisAgent to room <room-id> ...
[3/5] Connecting HypothesisAgent to room <room-id> ...
[4/5] ReproAgent → @HypothesisAgent: sending evidence ...
[5/5] Waiting for HypothesisAgent echo (timeout 30s) ...

  [HypothesisAgent] << received from ReproAgent (...): 'ran all 4 steps ...'
  [HypothesisAgent] evidence logged — posting placeholder diagnosis ...
  [HypothesisAgent] >> sent to ReproAgent: '@hanschundekad/reproagent confirmed ...'

  [ReproAgent stand-in] << echo from HypothesisAgent:
      '@hanschundekad/reproagent confirmed, matches the report. Root cause: ...'
=== ECHO LOOP COMPLETE ===
```

If `BAND_ROOM_ID` was unset, note the printed room ID; setting it in `.env` keeps all three agents in ONE room. (If it fails live, STOP and debug with `superpowers:systematic-debugging`; do not paper over it.)

- [ ] **Step 5: Commit**

```bash
git add scripts/hypothesis_echo_demo.py
git commit -m "feat: live HypothesisAgent echo demo — ReproAgent ↔ HypothesisAgent (Phase 3)"
```

---

## Self-Review

**Spec coverage:**
- Connect as `BAND_HYPOTHESIS_*` identity → `run()` uses `cfg.band_hypothesis`. ✅
- Join shared `BAND_ROOM_ID` → `connect(room_id=cfg.band_room_id)`. ✅
- Run on WebSocket subscription, stay alive indefinitely → `await asyncio.Event().wait()` in `run()`; `__main__` blocks forever. ✅
- Echo on @mention from ReproAgent: log evidence, post ONE hardcoded HypothesisPayload @mentioning ReproAgent → `make_echo_callback` (sender filter + single `send_message`). ✅
- Placeholder uses the shared schema shape → `PLACEHOLDER_HYPOTHESIS = HypothesisPayload(...)`. ✅
- Prints everything sent/received → `print` on receive, on send, and in the stand-in. ✅
- Named exactly `HypothesisAgent`; every message @mentions a target; messages not events. ✅
- Imports shared module, doesn't modify it; no Claude; no browser. ✅
- Three-way proof deferred to main reconciliation; this worktree proves the HypothesisAgent slice live (2 WebSockets). ✅ (per user's chosen scope)

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows full code. ✅

**Type consistency:** `make_echo_callback(repro_agent_id)` / `PLACEHOLDER_HYPOTHESIS` / `run(cfg)` names identical across agent.py, `__init__.py`, `__main__.py`, the demo, and tests. `BandAgent.send_message(mentions=[...], text=...)` and `add_participant(name)` match the shipped shared module signatures. ✅
