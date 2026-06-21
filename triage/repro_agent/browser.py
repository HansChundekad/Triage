"""ReproAgent — real Browserbase/Stagehand browser execution (Phase 4).

Two-part module:
  Part 2 (detect_bug) — pure function, unit-testable, easy to tune.
  Part 1 (run_repro)  — full async session lifecycle, calls detect_bug.

SDK note: `stagehand` v3.21.0 starts a session against a Browserbase cloud
browser and exposes an async API. `playwright` connects via CDP for
screenshots + console capture. Both point at the same cloud browser.
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
# Tune BLANK_BODY_THRESHOLD and CRASH_SUBSTRING here.
# ---------------------------------------------------------------------------

# Body text shorter than this (after stripping) is considered blank/crashed.
# 10 chosen so the test fixture "My Tasks\n  test task\nAdd Delete" (34 chars)
# is correctly classified as non-blank; a real crash page renders ~0 chars.
BLANK_BODY_THRESHOLD = 10

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
                logger.info(
                    "[ReproAgent] act '%s': %s — %s",
                    step_label,
                    "OK" if act_ok else "FAIL",
                    act_msg,
                )

                # Screenshot after each step
                await asyncio.sleep(0.5)  # brief settle before capture
                try:
                    screenshot_bytes = await page.screenshot()
                    b64 = base64.b64encode(screenshot_bytes).decode()
                    screenshots.append(b64)
                    evidence.append(
                        f"Screenshot after '{step_label}': captured ({len(screenshot_bytes)} bytes)"
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[ReproAgent] screenshot failed after '%s': %s", step_label, exc
                    )
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

            evidence.append(
                f"Extracted body text ({len(body_text)} chars): {body_text[:200]!r}"
            )
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
