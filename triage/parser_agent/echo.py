"""ParserAgent echo logic (Phase 3).

Pure, deterministic helpers — no Band connection, no I/O. Phase 3 is an echo
only: hardcoded placeholder steps, no real parsing (that is Phase 5).
"""
from __future__ import annotations

from triage.shared.band import AgentName, ReproStepsPayload

# Hardcoded placeholder steps — Phase 3 does NOT parse anything real.
PLACEHOLDER_STEPS: list[str] = [
    "focus input",
    "type task",
    "click add",
    "click delete",
]


def build_repro_steps_payload(issue_url: str) -> ReproStepsPayload:
    """Build the hardcoded placeholder repro-steps payload."""
    return ReproStepsPayload(issue_url=issue_url, steps=list(PLACEHOLDER_STEPS))


def format_steps_message(payload: ReproStepsPayload) -> str:
    """Render the structured-steps payload as the directed @ReproAgent message.

    Routing is done by the structured ``mentions`` arg passed to
    ``BandAgent.send_message``; the ``@ReproAgent`` prefix here is the
    human-readable transcript text.
    """
    return (
        f"@ReproAgent extracted {len(payload.steps)} steps: "
        f"{', '.join(payload.steps)} (issue: {payload.issue_url})"
    )


def sender_agent_name(sender_id: str, cfg) -> AgentName | None:
    """Map a Band sender UUID to its agent name, or None if unknown.

    ``cfg`` is duck-typed: only ``band_parser``/``band_repro``/``band_hypothesis``
    ``.agent_id`` are read (so tests can pass a lightweight stub).
    """
    by_id: dict[str, AgentName] = {
        cfg.band_parser.agent_id: "ParserAgent",
        cfg.band_repro.agent_id: "ReproAgent",
        cfg.band_hypothesis.agent_id: "HypothesisAgent",
    }
    return by_id.get(sender_id)
