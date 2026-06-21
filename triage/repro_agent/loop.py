"""ReproAgent retry-loop logic — pure, unit-testable, no browser/Band/network.

This module decides WHAT to do with an incoming Band message (parse steps,
retry, confirm, ignore) and tracks loop state. Browser work stays in
browser.py; Band I/O stays in echo.py. Keeping the decisions here means the
loop-safety guarantees are testable without a live session.
"""
from __future__ import annotations

import re

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
