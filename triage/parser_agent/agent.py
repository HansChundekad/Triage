"""ParserAgent orchestration — Band callback glue, message formatting, redirect.

Pure helpers (formatting, sender mapping) plus the async orchestration that
fetches + parses + posts. No browser work lives here.
"""
from __future__ import annotations

import logging

from triage.shared.band import AgentName, ReproStepsPayload

logger = logging.getLogger(__name__)


def format_steps_message(payload: ReproStepsPayload) -> str:
    """Render the structured steps as the directed @ReproAgent message.

    Format (the contract ReproAgent's parser reads): a header line, then one
    numbered line per step matching ``^\\s*\\d+\\.\\s+(.*)$``.
    """
    lines = [f"@ReproAgent repro steps for {payload.issue_url}:"]
    for index, step in enumerate(payload.steps, start=1):
        lines.append(f"{index}. {step}")
    return "\n".join(lines)


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
