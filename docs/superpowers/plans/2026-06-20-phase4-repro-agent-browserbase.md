# Phase 4 — ReproAgent Real Browserbase Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ReproAgent's hardcoded Phase 3 echo with a real Browserbase/Stagehand session that drives the live buggy to-do app through 4 repro steps, captures screenshots and console errors, detects the bug using dual-signal logic, and reports real evidence @mentioning HypothesisAgent.

**Architecture:** ReproAgent's existing Band wiring stays untouched. A new `browser.py` module handles the full Browserbase session lifecycle using `AsyncStagehand` (native async, no thread wrappers needed). A separate `playwright` CDP connection to the same session captures screenshots and console errors that stagehand doesn't expose. `echo.py`'s handler drops the fake result and calls `run_repro()` instead.

**Tech Stack:** `stagehand` v3.21.0 (already installed, SEA binary bundled), `playwright` (new dep, CDP-only, no local browser needed), `asyncio`, existing Band layer.

## Global Constraints

- All browser work stays in `triage/repro_agent/` — never in ParserAgent or HypothesisAgent
- Agent named exactly `ReproAgent`
- New Browserbase session per repro attempt — never reuse `session_id`
- TDD: write the failing test before writing impl
- Python 3.11+ (dev on 3.14)
- Use repo venv: `.venv/bin/pip`, `.venv/bin/pytest`
- Per-task commits, scoped messages, no secrets committed

## SDK Drift vs TRIAGE_INTEGRATIONS.md — read before touching integration code

The integration doc lists MCP tool names (`browserbase_stagehand_act` etc.) — those are for the LLM-tool-use path (Claude Code using MCP). **Our Python code uses the `stagehand` Python SDK directly, which has a completely different API:**

| Doc says (MCP) | Python SDK actually uses |
|---|---|
| `browserbase_session_create` | `await client.sessions.start(model_name=..., browser={"type": "browserbase"})` |
| `browserbase_stagehand_navigate` | `await session.navigate(url=...)` |
| `browserbase_stagehand_observe` | `await session.observe(instruction=...)` |
| `browserbase_stagehand_act` | `await session.act(input=...)` |
| `browserbase_stagehand_extract` | `await session.extract(instruction=..., schema={...})` |
| `browserbase_session_close` | `await session.end()` |
| `browserbase_screenshot` | **Not in stagehand SDK** — use Playwright via `session.data.cdp_url` |

The stagehand SDK starts a local SEA binary (`stagehand-darwin-arm64`) that handles the Browserbase connection internally. `AsyncStagehand` sends HTTP to this local process. `session.data.cdp_url` is the CDP WebSocket URL of the live Browserbase browser, which we connect Playwright to for screenshot + console capture.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `triage/repro_agent/browser.py` | **CREATE** | Full browser execution: `DetectionResult`, `detect_bug()`, `run_repro()` |
| `tests/test_repro_browser.py` | **CREATE** | Unit tests for `detect_bug()` — no live browser, pure logic |
| `triage/repro_agent/echo.py` | **MODIFY** | Replace `build_fake_result()` with `await run_repro(cfg)` in handler |
| `pyproject.toml` | **MODIFY** | Add `playwright` to dependencies |
| `triage/repro_agent/__main__.py` | **NO CHANGE** | Already correct |
| `triage/shared/band.py` | **NO CHANGE** | `ReproResultPayload` already has the right fields |

---

## Task 1: Add `playwright` dependency

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `playwright` available in venv for `from playwright.async_api import async_playwright`

- [ ] **Step 1: Add playwright to pyproject.toml**

In `pyproject.toml`, add `"playwright",` after `"stagehand",` in the dependencies list:

```toml
dependencies = [
    "python-dotenv>=1.0",
    "anthropic",
    "httpx",
    "band-sdk",
    "stagehand",
    "playwright",                                  # CDP screenshots + console errors (ReproAgent)
    "arize-phoenix",
    "openinference-instrumentation-anthropic",
    "opentelemetry-sdk",
]
```

- [ ] **Step 2: Install the updated package**

```bash
.venv/bin/pip install -e ".[dev]"
```

Expected: `Successfully installed playwright-...` (or already satisfied for others)

- [ ] **Step 3: Verify import works**

```bash
.venv/bin/python -c "from playwright.async_api import async_playwright; from stagehand import AsyncStagehand; print('OK')"
```

Expected: `OK`

Note: we do NOT run `playwright install chromium`. We're using CDP to connect to a remote Browserbase browser — no local browser binary needed.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat(repro): add playwright for CDP screenshots + console capture"
```

---

## Task 2: Scaffold `browser.py` and write failing detection tests (TDD)

**Files:**
- Create: `triage/repro_agent/browser.py`
- Create: `tests/test_repro_browser.py`

**Interfaces:**
- Produces:
  - `DetectionResult(bug_detected: bool, blank_body: bool, console_match: bool)`
  - `detect_bug(body_text: str, console_errors: list[str]) -> DetectionResult`

- [ ] **Step 1: Write the failing tests first**

Create `tests/test_repro_browser.py`:

```python
"""Unit tests for ReproAgent bug-detection logic.

These tests are pure logic — no browser, no network, no env vars.
They exercise detect_bug() with synthetic inputs so the thresholds
are verifiable and tunable without a live session.
"""
import pytest
from triage.repro_agent.browser import DetectionResult, detect_bug

CRASH_ERROR = "TypeError: Cannot read properties of undefined (reading 'map')"
OTHER_ERROR = "TypeError: something unrelated"
BLANK_BODY = "   "
RICH_BODY = "My Tasks\n  test task\nAdd Delete"


def test_both_signals_true_detects_bug():
    result = detect_bug(body_text=BLANK_BODY, console_errors=[CRASH_ERROR])
    assert result.bug_detected is True
    assert result.blank_body is True
    assert result.console_match is True


def test_blank_body_only_does_not_detect():
    result = detect_bug(body_text=BLANK_BODY, console_errors=[])
    assert result.bug_detected is False
    assert result.blank_body is True
    assert result.console_match is False


def test_console_match_only_does_not_detect():
    result = detect_bug(body_text=RICH_BODY, console_errors=[CRASH_ERROR])
    assert result.bug_detected is False
    assert result.blank_body is False
    assert result.console_match is True


def test_neither_signal_does_not_detect():
    result = detect_bug(body_text=RICH_BODY, console_errors=[OTHER_ERROR])
    assert result.bug_detected is False


def test_partial_console_error_string_still_matches():
    # The real error may have extra context — match on substring
    partial = "Cannot read properties of undefined"
    result = detect_bug(body_text=BLANK_BODY, console_errors=[f"TypeError: {partial} (reading 'map')"])
    assert result.console_match is True


def test_multiple_errors_any_match_counts():
    result = detect_bug(
        body_text=BLANK_BODY,
        console_errors=[OTHER_ERROR, CRASH_ERROR],
    )
    assert result.bug_detected is True


def test_whitespace_only_body_is_blank():
    result = detect_bug(body_text="\n  \t  \n", console_errors=[CRASH_ERROR])
    assert result.blank_body is True


def test_returns_detection_result_type():
    result = detect_bug(body_text=BLANK_BODY, console_errors=[CRASH_ERROR])
    assert isinstance(result, DetectionResult)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_repro_browser.py -v
```

Expected: `ERROR` or `ImportError` — `triage.repro_agent.browser` doesn't exist yet.

- [ ] **Step 3: Create `triage/repro_agent/browser.py` with just the detection logic**

```python
"""ReproAgent — real Browserbase/Stagehand browser execution (Phase 4).

Two-part module:
  Part 2 (detect_bug) — pure function, unit-testable, easy to tune.
  Part 1 (run_repro)  — full async session lifecycle, calls detect_bug.
"""
from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Bug detection — Part 2
# Dual-signal: BOTH must be true for bug_detected=True.
# Tune BLANK_BODY_THRESHOLD and CRASH_SUBSTRING here.
# ---------------------------------------------------------------------------

# Body text shorter than this (after stripping) is considered blank/crashed.
BLANK_BODY_THRESHOLD = 50

# The expected JavaScript crash fingerprint (substring match).
CRASH_SUBSTRING = "Cannot read properties of undefined"


@dataclass
class DetectionResult:
    bug_detected: bool
    blank_body: bool      # signal A: page body went empty
    console_match: bool   # signal B: crash error matched in console output


def detect_bug(body_text: str, console_errors: list[str]) -> DetectionResult:
    """Decide whether the planted bug fired, using two independent signals.

    Args:
        body_text:      Visible text extracted from the page body after the
                        final repro step (via stagehand extract).
        console_errors: All console error + pageerror strings captured during
                        the session (via Playwright event listeners).

    Returns:
        DetectionResult with bug_detected=True only when BOTH signals fire.
    """
    blank_body = len(body_text.strip()) < BLANK_BODY_THRESHOLD
    console_match = any(CRASH_SUBSTRING in err for err in console_errors)
    return DetectionResult(
        bug_detected=blank_body and console_match,
        blank_body=blank_body,
        console_match=console_match,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_repro_browser.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add triage/repro_agent/browser.py tests/test_repro_browser.py
git commit -m "feat(repro): TDD — DetectionResult + detect_bug with dual-signal logic"
```

---

## Task 3: Implement `run_repro()` — full Part 1 browser execution

**Files:**
- Modify: `triage/repro_agent/browser.py` (add `run_repro`, imports, constants)

**Interfaces:**
- Consumes:
  - `Config` from `triage.config` (fields: `browserbase_api_key`, `anthropic_api_key`, `app_url`)
  - `ReproResultPayload` from `triage.shared.band`
  - `DetectionResult`, `detect_bug` (already in this file)
- Produces:
  - `async def run_repro(cfg: Config) -> ReproResultPayload`

**Repro steps (hardcoded for Phase 4 — parser integration is Phase 5):**

| Step label | observe instruction | act instruction |
|---|---|---|
| focus input | `"find the task text input field"` | `"click the task text input field to focus it"` |
| type task | *(no observe needed)* | `"type 'test task' into the focused input field"` |
| click add | `"find the Add button to submit the task"` | `"click the Add button to add the task to the list"` |
| click delete | `"find the Delete button next to the task item"` | `"click the Delete button to remove the task"` |

- [ ] **Step 1: Add imports and `run_repro` to `browser.py`**

Replace the full content of `triage/repro_agent/browser.py` with:

```python
"""ReproAgent — real Browserbase/Stagehand browser execution (Phase 4).

Two-part module:
  Part 2 (detect_bug) — pure function, unit-testable, easy to tune.
  Part 1 (run_repro)  — full async session lifecycle, calls detect_bug.

SDK note: `stagehand` v3.21.0 starts a local SEA binary and exposes an
async HTTP API. `playwright` connects via CDP for screenshots + console
capture. Both point at the same Browserbase cloud browser.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from triage.config import Config

from triage.shared.band import ReproResultPayload

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bug detection — Part 2
# Dual-signal: BOTH must be true for bug_detected=True.
# Tune BLANK_BODY_THRESHOLD and CRASH_SUBSTRING here without touching run_repro.
# ---------------------------------------------------------------------------

BLANK_BODY_THRESHOLD = 50
CRASH_SUBSTRING = "Cannot read properties of undefined"


@dataclass
class DetectionResult:
    bug_detected: bool
    blank_body: bool
    console_match: bool


def detect_bug(body_text: str, console_errors: list[str]) -> DetectionResult:
    """Decide whether the planted bug fired using two independent signals.

    Args:
        body_text:      Visible text extracted from the page body after the
                        final repro step (via stagehand extract).
        console_errors: All console error + pageerror strings captured during
                        the session (via Playwright event listeners).

    Returns:
        DetectionResult with bug_detected=True only when BOTH signals fire.
    """
    blank_body = len(body_text.strip()) < BLANK_BODY_THRESHOLD
    console_match = any(CRASH_SUBSTRING in err for err in console_errors)
    return DetectionResult(
        bug_detected=blank_body and console_match,
        blank_body=blank_body,
        console_match=console_match,
    )


# ---------------------------------------------------------------------------
# Repro steps — hardcoded for Phase 4 (real parsing arrives in Phase 5)
# Each tuple: (label, observe_instruction_or_None, act_instruction)
# ---------------------------------------------------------------------------

_STEPS: list[tuple[str, str | None, str]] = [
    (
        "focus input",
        "find the task text input field",
        "click the task text input field to focus it",
    ),
    (
        "type task",
        None,  # no observe needed — just type into the focused field
        "type 'test task' into the focused input field",
    ),
    (
        "click add",
        "find the Add button to submit the task",
        "click the Add button to add the task to the list",
    ),
    (
        "click delete",
        "find the Delete button next to the task item",
        "click the Delete button to remove the task",
    ),
]

# ---------------------------------------------------------------------------
# Part 1 — browser execution
# ---------------------------------------------------------------------------


async def run_repro(cfg: "Config") -> ReproResultPayload:
    """Open a real Browserbase session, execute repro steps, return evidence.

    Session lifecycle (per TRIAGE_INTEGRATIONS.md §2.4):
      1. start session  → get session_id + cdp_url
      2. connect Playwright CDP → register console listeners
      3. navigate to live app
      4. for each step: observe (if applicable) → act → screenshot
      5. extract body text
      6. detect bug
      7. end session + disconnect Playwright
      8. return ReproResultPayload

    A new Browserbase session is created every call — never reused.
    """
    from stagehand import AsyncStagehand
    from playwright.async_api import async_playwright

    session_id: str = ""
    session_url: str = ""
    evidence: list[str] = []
    console_errors: list[str] = []
    screenshots: list[str] = []  # base64-encoded PNGs, one per step

    client = AsyncStagehand(
        browserbase_api_key=cfg.browserbase_api_key,
        model_api_key=cfg.anthropic_api_key,
    )
    try:
        # --- 1. Start Browserbase session ---
        logger.info("[ReproAgent] starting Browserbase session…")
        session = await client.sessions.start(
            model_name="anthropic/claude-sonnet-4-6",
            browser={"type": "browserbase"},
        )
        session_id = session.id
        session_url = f"https://www.browserbase.com/sessions/{session_id}"
        cdp_url = session.data.cdp_url
        logger.info("[ReproAgent] session %s — replay: %s", session_id, session_url)
        evidence.append(f"Browserbase session: {session_id}")
        evidence.append(f"Replay URL: {session_url}")

        # --- 2. Connect Playwright via CDP for screenshots + console capture ---
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0]
            page = context.pages[0]

            # Register listeners BEFORE navigation so we catch all events
            def _on_console(msg):
                if msg.type in ("error", "warning"):
                    console_errors.append(f"[{msg.type}] {msg.text}")

            def _on_pageerror(exc):
                console_errors.append(f"[pageerror] {exc}")

            page.on("console", _on_console)
            page.on("pageerror", _on_pageerror)

            # --- 3. Navigate to live app ---
            logger.info("[ReproAgent] navigating to %s", cfg.app_url)
            await session.navigate(url=cfg.app_url)
            await asyncio.sleep(1)  # let the page settle
            evidence.append(f"Navigated to: {cfg.app_url}")

            # --- 4. Execute repro steps: observe → act → screenshot ---
            for step_label, observe_instr, act_instr in _STEPS:
                logger.info("[ReproAgent] step: %s", step_label)
                await client.sessions.send_event if False else None  # type: ignore

                if observe_instr:
                    obs = await session.observe(instruction=observe_instr)
                    found = obs.data.result
                    if not found:
                        msg = f"Step '{step_label}': observe found no elements for: {observe_instr!r}"
                        logger.warning("[ReproAgent] %s", msg)
                        evidence.append(f"WARN — {msg}")
                    else:
                        evidence.append(f"Step '{step_label}': found {len(found)} element(s)")

                act_result = await session.act(input=act_instr)
                act_ok = act_result.data.result.success
                act_msg = act_result.data.result.message
                evidence.append(
                    f"Step '{step_label}' act: {'OK' if act_ok else 'FAIL'} — {act_msg}"
                )
                logger.info("[ReproAgent] act '%s': %s — %s", step_label, "OK" if act_ok else "FAIL", act_msg)

                # Screenshot after each step
                await asyncio.sleep(0.5)  # brief settle before capture
                try:
                    screenshot_bytes = await page.screenshot()
                    b64 = base64.b64encode(screenshot_bytes).decode()
                    screenshots.append(b64)
                    evidence.append(f"Screenshot after '{step_label}': captured ({len(screenshot_bytes)} bytes)")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[ReproAgent] screenshot failed after '%s': %s", step_label, exc)
                    evidence.append(f"Screenshot after '{step_label}': FAILED — {exc}")

            # --- 5. Extract body text for blank-page detection ---
            try:
                extract_resp = await session.extract(
                    instruction="Extract all visible text content from the page body",
                    schema={
                        "type": "object",
                        "properties": {"body_text": {"type": "string"}},
                        "required": ["body_text"],
                    },
                )
                raw = extract_resp.data.result
                body_text: str = raw.get("body_text", "") if isinstance(raw, dict) else str(raw)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[ReproAgent] body extract failed: %s", exc)
                body_text = ""
                evidence.append(f"Body extract failed: {exc}")

            evidence.append(f"Extracted body text ({len(body_text)} chars): {body_text[:200]!r}")
            logger.info("[ReproAgent] captured %d console errors", len(console_errors))

            await browser.close()

        # --- 6. Detect bug ---
        detection = detect_bug(body_text=body_text, console_errors=console_errors)
        evidence.append(
            f"Detection: bug_detected={detection.bug_detected} "
            f"(blank_body={detection.blank_body}, console_match={detection.console_match})"
        )
        logger.info("[ReproAgent] detection: %s", detection)

        # --- 7. End session ---
        await session.end()
        logger.info("[ReproAgent] session ended cleanly")

    finally:
        await client.close()

    return ReproResultPayload(
        success=detection.bug_detected,
        evidence=evidence,
        console_errors=console_errors,
        session_url=session_url,
    )
```

- [ ] **Step 2: Run existing tests to verify nothing broke**

```bash
.venv/bin/pytest -v
```

Expected: all 34 existing tests + 8 new detection tests = 42 PASS.  
(Detection tests import `detect_bug` from the updated file — should still pass.)

- [ ] **Step 3: Commit**

```bash
git add triage/repro_agent/browser.py
git commit -m "feat(repro): Part 1 — run_repro() full Browserbase/Stagehand session lifecycle"
```

---

## Task 4: Wire `run_repro()` into ReproAgent handler

**Files:**
- Modify: `triage/repro_agent/echo.py`

**Interfaces:**
- Consumes: `run_repro(cfg)` from `triage.repro_agent.browser`
- Produces: real `ReproResultPayload` (with live evidence) sent @HypothesisAgent via Band

- [ ] **Step 1: Update the handler in `triage/repro_agent/echo.py`**

Replace the full contents of `triage/repro_agent/echo.py` with:

```python
"""ReproAgent — Phase 4: real Browserbase/Stagehand execution.

Receives ParserAgent's step list via Band @mention, runs a live Browserbase
session, and reports real evidence @HypothesisAgent.

Band wiring (Phase 3, unchanged):
  - on_message callback: handle_parser_message
  - run(): connect, add_participant, listen loop
"""
from __future__ import annotations

import asyncio
import logging

from triage.config import load_config
from triage.repro_agent.browser import run_repro
from triage.shared.band import BandAgent, ReproResultPayload

logger = logging.getLogger(__name__)

_HYPOTHESIS_HANDLE = "@hanschundekad/hypothesisagent"


def format_result_message(result: ReproResultPayload) -> str:
    """Render a directed @HypothesisAgent message from a ReproResultPayload."""
    verdict = "BUG REPRODUCED" if result.success else "BUG NOT REPRODUCED"
    lines = [
        f"{_HYPOTHESIS_HANDLE} repro result:",
        f"verdict: {verdict}",
        f"session_url: {result.session_url}",
        "evidence:",
        *[f"  - {e}" for e in result.evidence],
        "console_errors:",
        *[f"  - {c}" for c in result.console_errors],
    ]
    return "\n".join(lines)


def _sender_is_hypothesis(sender_name: str | None) -> bool:
    return bool(sender_name and "hypothesis" in sender_name.lower())


async def handle_parser_message(payload, agent) -> None:
    """on_message callback: run real browser session and report @HypothesisAgent."""
    sender = getattr(payload, "sender_name", None)
    print(f"\n[ReproAgent] << received from {sender}:")
    print(f"    {payload.content!r}")

    if _sender_is_hypothesis(sender):
        print("[ReproAgent] sender is HypothesisAgent — ignoring (retry logic is Phase 6).")
        return

    print("[ReproAgent] launching real Browserbase session…")
    cfg = load_config()

    await agent.send_event("Starting Browserbase repro session", "task")

    try:
        result = await run_repro(cfg)
    except Exception as exc:  # noqa: BLE001
        logger.error("[ReproAgent] browser execution failed: %s", exc)
        await agent.send_event(f"Browser execution error: {exc}", "error")
        result = ReproResultPayload(
            success=False,
            evidence=[f"Execution error: {exc}"],
            console_errors=[],
            session_url="",
        )

    await agent.send_event(
        f"Repro complete — bug_detected={result.success}, "
        f"{len(result.console_errors)} console error(s)",
        "task",
    )

    text = format_result_message(result)
    print("[ReproAgent] >> sending real repro result @HypothesisAgent:")
    print(text[:500], "…" if len(text) > 500 else "")
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

    try:
        await agent.add_participant("HypothesisAgent")
        print("[ReproAgent] ensured HypothesisAgent is a room participant.")
    except Exception as exc:  # noqa: BLE001
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

- [ ] **Step 2: Update existing repro echo tests**

The existing `tests/test_repro_echo.py` tests `build_fake_result` and `format_result_message` from the old echo.py. Open `tests/test_repro_echo.py` and check which functions are tested. The `format_result_message` function still exists in the new echo.py, so tests importing it should pass. If tests import `build_fake_result`, remove those tests (it no longer exists). Run:

```bash
.venv/bin/pytest tests/test_repro_echo.py -v
```

If there are failures due to missing `build_fake_result`:
- Open `tests/test_repro_echo.py`
- Remove any test that imports or calls `build_fake_result`
- Add a smoke test for the new `format_result_message` with a real `ReproResultPayload`:

```python
def test_format_result_message_bug_detected():
    result = ReproResultPayload(
        success=True,
        evidence=["step 1 ok", "detected: blank_body=True"],
        console_errors=["TypeError: Cannot read properties of undefined"],
        session_url="https://www.browserbase.com/sessions/abc123",
    )
    msg = format_result_message(result)
    assert "@hanschundekad/hypothesisagent" in msg
    assert "BUG REPRODUCED" in msg
    assert "abc123" in msg
```

- [ ] **Step 3: Run full test suite**

```bash
.venv/bin/pytest -v
```

Expected: all tests pass (may be 42+ depending on what was removed/added).

- [ ] **Step 4: Commit**

```bash
git add triage/repro_agent/echo.py tests/test_repro_echo.py
git commit -m "feat(repro): wire run_repro() into Band handler — replace Phase 3 echo"
```

---

## Task 5: Live end-to-end run — Part 1 checkpoint (USER REVIEWS)

> This task is not automated — it requires a live Browserbase session. Run it and share the output with the user before proceeding to Part 2 tuning.

**Pre-flight checklist:**
- [ ] `.env` has `BROWSERBASE_API_KEY`, `BROWSERBASE_PROJECT_ID`, `ANTHROPIC_API_KEY`, `TRIAGE_APP_URL` all set
- [ ] `BAND_REPRO_API_KEY`, `BAND_REPRO_AGENT_ID`, `BAND_ROOM_ID` set (or BAND_ROOM_ID empty and a new room will be created)

**Step 1: Run ReproAgent standalone**

In one terminal, start ReproAgent:
```bash
.venv/bin/python -m triage.repro_agent
```

Expected output:
```
[ReproAgent] connected to room <room_id>. Listening for @mentions. Ctrl-C to stop.
```

**Step 2: Send a test @mention to trigger the repro**

In a second terminal, run a quick trigger script (no ParserAgent needed for this test):

```bash
.venv/bin/python - <<'EOF'
import asyncio
from triage.config import load_config
from triage.shared.band import BandAgent

async def main():
    cfg = load_config()
    agent = BandAgent("ParserAgent", cfg.band_parser.agent_id, cfg.band_parser.api_key)
    room_id = await agent.connect(room_id=cfg.band_room_id)
    await agent.add_participant("ReproAgent")
    await asyncio.sleep(1)
    await agent.send_message(
        ["ReproAgent"],
        "@hanschundekad/reproagent extracted 4 steps: focus input, type task, click add, click delete (issue: https://github.com/test/test/issues/1)"
    )
    print(f"Sent trigger to room {room_id}")
    await agent.disconnect()

asyncio.run(main())
EOF
```

**Step 3: Watch ReproAgent's terminal output**

You should see (in order):
1. `[ReproAgent] << received from ParserAgent`
2. `[ReproAgent] launching real Browserbase session…`
3. `[ReproAgent] starting Browserbase session…` — SEA binary boots (~5-10s first time)
4. `[ReproAgent] session <id> — replay: https://www.browserbase.com/sessions/<id>`
5. `[ReproAgent] navigating to <app_url>`
6. Per-step logs for focus/type/add/delete
7. `[ReproAgent] captured N console errors`
8. `[ReproAgent] detection: DetectionResult(bug_detected=..., blank_body=..., console_match=...)`
9. `[ReproAgent] session ended cleanly`
10. `[ReproAgent] >> sending real repro result @HypothesisAgent:`

**Step 4: Open the session replay**

Open `https://www.browserbase.com/sessions/<session_id>` in a browser. You should see:
- The real to-do app loading
- Text being typed
- Add button clicked → task appears
- Delete button clicked → app goes blank (the crash)

**Step 5: User reviews and decides on Part 2 tuning**

Based on the output, check:
- Were all 4 steps executed? (`evidence` list in the Band message)
- Were console errors captured? (contents of `console_errors`)
- What did `body_text` contain after the crash?
- Was `bug_detected=True`?

> **STOP HERE** — share output with user. Part 2 detection thresholds (`BLANK_BODY_THRESHOLD`, `CRASH_SUBSTRING` in `browser.py`) should be tuned based on actual observed values before declaring Phase 4 complete.

---

## Self-Review Against Phase 4 Spec

| Requirement | Covered by | Status |
|---|---|---|
| Real Browserbase session with sessionId | Task 3: `client.sessions.start()` | ✅ |
| Replay URL `https://www.browserbase.com/sessions/{id}` | Task 3: constructed from `session.id` | ✅ |
| Navigate to live app URL from env | Task 3: `session.navigate(url=cfg.app_url)` | ✅ |
| observe before act for each step | Task 3: `_STEPS` tuples with observe_instr | ✅ |
| 4 hardcoded steps: focus, type, add, delete | Task 3: `_STEPS` list | ✅ |
| Screenshot after each step | Task 3: `page.screenshot()` via Playwright CDP | ✅ |
| Capture console errors | Task 3: `page.on("console", ...)` + `page.on("pageerror", ...)` | ✅ |
| Close session cleanly | Task 3: `session.end()` + `client.close()` in `finally` | ✅ |
| Bug detection signal A: blank body via extract | Task 2+3: `detect_bug` + `session.extract()` | ✅ |
| Bug detection signal B: console error match | Task 2+3: `detect_bug` + Playwright listeners | ✅ |
| Detection logic readable + tunable constants | Task 2: `BLANK_BODY_THRESHOLD`, `CRASH_SUBSTRING` at top of file | ✅ |
| ReproAgent posts real evidence @HypothesisAgent | Task 4: `format_result_message` + `send_message` | ✅ |
| Band wiring from Phase 3 intact | Task 4: `run()`, `add_participant`, `listen loop` preserved | ✅ |
| All browser work in ReproAgent only | Single file: `triage/repro_agent/browser.py` | ✅ |
| New session per attempt | Task 3: `sessions.start()` called fresh each `run_repro()` | ✅ |
| Named exactly ReproAgent | Task 4: `BandAgent(name="ReproAgent", ...)` | ✅ |
| Part 1 checkpoint before Part 2 tuning | Task 5: live run before completion | ✅ |
