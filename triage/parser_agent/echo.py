"""ParserAgent echo logic (Phase 3).

Pure, deterministic helpers — no Band connection, no I/O. Phase 3 is an echo
only: hardcoded placeholder steps, no real parsing (that is Phase 5).
"""
from __future__ import annotations

import logging

from triage.shared.band import AgentName, ReproStepsPayload

logger = logging.getLogger(__name__)

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


def make_on_message(cfg):
    """Build the async on_message callback ParserAgent passes to BandAgent.

    Logs the sender + content, and acks the sender via @mention when the
    sender is a known agent (ReproAgent / HypothesisAgent). Unknown or
    unmappable senders are logged but not acked.
    """

    async def on_message(payload, agent) -> None:
        name = sender_agent_name(payload.sender_id, cfg) or payload.sender_name
        print(f"[ParserAgent] << received from {name}: {payload.content!r}")
        logger.info("ParserAgent received from %s: %s", name, payload.content)

        target = sender_agent_name(payload.sender_id, cfg)
        if target in ("ReproAgent", "HypothesisAgent"):
            ack = f"@{target} ack — ParserAgent received your message (echo)."
            print(f"[ParserAgent] >> ack to {target}: {ack!r}")
            await agent.send_message([target], ack)

    return on_message
