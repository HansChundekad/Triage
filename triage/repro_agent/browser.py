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
import os
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
# Part 1 — browser execution
# ---------------------------------------------------------------------------


async def run_repro(
    cfg: "Config",
    steps: list[str],
    tweak: str | None = None,
    *,
    run_trace=None,
    artifacts=None,
    attempt: int = 1,
    browser_execution_span=None,
) -> ReproResultPayload:
    """Open a fresh Browserbase session, execute `steps`, return evidence.

    `steps` are natural-language instructions from ParserAgent (one Stagehand
    observe+act per step). `tweak`, when set, is retry guidance from
    HypothesisAgent appended to each act instruction.

    Session lifecycle (per TRIAGE_INTEGRATIONS.md §2.4):
      1. start session  → get session_id + cdp_url
      2. connect Playwright CDP → register console listeners
      3. navigate to live app
      4. for each step: observe → act → screenshot
      5. extract body text
      6. detect bug
      7. end session + disconnect Playwright
      8. return ReproResultPayload

    A new Browserbase session is created every call — never reused (§2.4).
    """
    from stagehand import AsyncStagehand
    from playwright.async_api import async_playwright

    from triage.tracing.run_context import NullRunTrace, set_span_ok
    from triage.tracing.artifacts import NullRunArtifacts
    run_trace = run_trace if run_trace is not None else NullRunTrace()
    artifacts = artifacts if artifacts is not None else NullRunArtifacts()

    session_id: str = ""
    session_url: str = ""
    evidence: list[str] = []
    console_errors: list[str] = []
    screenshots: list[str] = []  # base64-encoded PNGs, one per step
    detection = DetectionResult(bug_detected=False, blank_body=False, console_match=False)

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
        # Prominent, demo-visible live view: while the session is ACTIVE this page
        # streams the real browser live; it becomes the replay once the session ends.
        # Each attempt is a fresh session, so this prints once per attempt.
        print(
            "\n  ┌─ 🌐 BROWSERBASE LIVE VIEW "
            f"(attempt {attempt}) ───────────────────────────\n"
            f"  │  watch the browser click through live (replay after it ends):\n"
            f"  │  {session_url}\n"
            "  └──────────────────────────────────────────────────────────────\n",
            flush=True,
        )
        # Demo convenience (opt-in via TRIAGE_OPEN_LIVE_VIEW=1, set by scripts/demo.sh):
        # pop each attempt's live view in a new browser tab so the presenter never has
        # to return to the terminal for the per-retry URL. Opens the native Browserbase
        # dashboard — nothing embedded. Guarded so it can never wedge a run.
        if os.environ.get("TRIAGE_OPEN_LIVE_VIEW") == "1":
            try:
                import webbrowser
                webbrowser.open(session_url)
            except Exception:  # noqa: BLE001 — a convenience must never break the run
                pass
        logger.info("[ReproAgent] session %s — live/replay: %s", session_id, session_url)
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
            for index, step in enumerate(steps, start=1):
                with run_trace.child_span("stagehand_action", browser_execution_span) as step_span:
                    step_label = f"step {index}: {step[:48]}"
                    act_instr = step if not tweak else f"{step}. Adjustment for this retry: {tweak}"
                    logger.info("[ReproAgent] %s", step_label)

                    obs = await session.observe(instruction=step)
                    found = obs.data.result
                    if not found:
                        msg = f"{step_label}: observe found no elements for: {step!r}"
                        logger.warning("[ReproAgent] %s", msg)
                        evidence.append(f"WARN — {msg}")
                    else:
                        evidence.append(f"{step_label}: found {len(found)} element(s)")

                    act_result = await session.act(input=act_instr)
                    act_ok = act_result.data.result.success
                    act_msg = act_result.data.result.message
                    evidence.append(
                        f"{step_label} act: {'OK' if act_ok else 'FAIL'} — {act_msg}"
                    )
                    logger.info(
                        "[ReproAgent] act '%s': %s — %s",
                        step_label,
                        "OK" if act_ok else "FAIL",
                        act_msg,
                    )

                    # Screenshot after each step
                    await asyncio.sleep(0.5)  # brief settle before capture
                    screenshot_ref = ""
                    try:
                        screenshot_bytes = await page.screenshot()
                        b64 = base64.b64encode(screenshot_bytes).decode()
                        screenshots.append(b64)
                        screenshot_ref = artifacts.save_screenshot(attempt, index, b64)
                        evidence.append(
                            f"Screenshot after '{step_label}': captured ({len(screenshot_bytes)} bytes)"
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "[ReproAgent] screenshot failed after '%s': %s", step_label, exc
                        )
                        evidence.append(f"Screenshot after '{step_label}': FAILED — {exc}")

                    if step_span is not None:
                        last_err = next(
                            (e for e in reversed(console_errors) if CRASH_SUBSTRING in e),
                            console_errors[-1] if console_errors else "",
                        )
                        step_span.set_attribute("step.index", index)
                        step_span.set_attribute("step.text", step)
                        step_span.set_attribute("action.success", bool(act_ok))
                        step_span.set_attribute("screenshot.ref", screenshot_ref)
                        step_span.set_attribute("console.error", last_err)
                        set_span_ok(step_span, bool(act_ok))

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
