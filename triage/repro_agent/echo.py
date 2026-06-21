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
