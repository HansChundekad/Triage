"""ReproAgent retry-loop logic — pure, unit-testable, no browser/Band/network.

This module decides WHAT to do with an incoming Band message (parse steps,
retry, confirm, ignore) and tracks loop state. Browser work stays in
browser.py; Band I/O stays in echo.py. Keeping the decisions here means the
loop-safety guarantees are testable without a live session.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

# One numbered step per line, e.g. "1. Click the Add button". Matches the
# block ParserAgent emits in format_steps_message (parser_agent/agent.py).
_STEP_LINE = re.compile(r"^\s*\d+\.\s+(.+?)\s*$")


def parse_steps(content: str) -> list[str]:
    """Extract natural-language repro steps from a ParserAgent message.

    Returns one string per numbered line, in order. Returns [] when the
    message has no numbered lines (e.g. a free-text redirect).
    """
    steps: list[str] = []
    for line in content.splitlines():
        match = _STEP_LINE.match(line)
        if match:
            steps.append(match.group(1).strip())
    return steps


# --- Loop-safety knob -------------------------------------------------------
# Hard cap on total browser attempts per repro cycle (initial run + retries).
# THIS is the single dial to tune. 3 = initial attempt + up to 2 retries.
MAX_REPRO_ATTEMPTS = 3
# ---------------------------------------------------------------------------

MessageKind = Literal["steps", "redirect", "confirm", "ignore"]

# Confirm markers — must agree with hypothesis_agent/agent.py::
# format_diagnosis_message confirm branch. See "cross-agent text contract".
_CONFIRM_MARKERS = ("repro valid", "confirmed, matches the report")

# Strip a leading "@handle " and a trailing "(suspected cause: ...)" so the
# core redirect instruction remains.
_LEADING_HANDLE = re.compile(r"^\s*@\S+\s+")
_SUSPECTED_CAUSE = re.compile(r"\s*\(suspected cause:.*\)\s*$", re.IGNORECASE | re.DOTALL)


def is_confirm(content: str) -> bool:
    """True when a HypothesisAgent message is a repro-confirmation (terminal)."""
    low = content.lower()
    return any(marker in low for marker in _CONFIRM_MARKERS)


def extract_tweak(content: str) -> str:
    """Pull the retry instruction out of a HypothesisAgent redirect message."""
    text = _LEADING_HANDLE.sub("", content, count=1)
    text = _SUSPECTED_CAUSE.sub("", text)
    return text.strip()


def classify_message(
    sender_id: str | None,
    content: str,
    parser_id: str,
    hypothesis_id: str,
) -> MessageKind:
    """Decide how ReproAgent should treat an incoming Band message.

    By sender identity (robust — not name heuristics):
      ParserAgent + numbered steps -> "steps"   (start / restart a cycle)
      HypothesisAgent + confirm     -> "confirm" (terminal success)
      HypothesisAgent + otherwise   -> "redirect"(retry with tweak)
      anything else                 -> "ignore"
    """
    if sender_id == parser_id:
        return "steps" if parse_steps(content) else "ignore"
    if sender_id == hypothesis_id:
        return "confirm" if is_confirm(content) else "redirect"
    return "ignore"


@dataclass
class ReproLoopState:
    """Per-cycle retry state, held by the ReproAgent message callback."""

    steps: list[str] = field(default_factory=list)
    attempts: int = 0
    max_attempts: int = MAX_REPRO_ATTEMPTS
    terminal: bool = False
    session_urls: list[str] = field(default_factory=list)  # one per attempt (Phase 7)

    @property
    def attempts_exhausted(self) -> bool:
        return self.attempts >= self.max_attempts

    def reset(self, steps: list[str]) -> None:
        """Begin a fresh repro cycle (new Parser steps / re-parse)."""
        self.steps = steps
        self.attempts = 0
        self.terminal = False
        self.session_urls = []


# HypothesisAgent handle for the directed give-up message (must match the
# handle used in echo.format_result_message — both point at HypothesisAgent).
_HYPOTHESIS_HANDLE = "@hanschundekad/hypothesisagent"


def format_giveup_message(state: ReproLoopState) -> str:
    """Final 'could not reproduce' message when the retry cap is reached.

    @mentions HypothesisAgent (required for visibility) and lists every
    attempt's session replay URL so Phase 7 can trace the full progression.
    """
    lines = [
        f"{_HYPOTHESIS_HANDLE} could not reproduce after {state.attempts} attempt(s). "
        f"Stopping — retry cap ({state.max_attempts}) reached.",
        "session replays:",
        *[f"  - {url}" for url in state.session_urls],
    ]
    return "\n".join(lines)
