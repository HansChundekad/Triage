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
