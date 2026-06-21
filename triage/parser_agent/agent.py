"""ParserAgent orchestration — Band callback glue, message formatting, redirect.

Pure helpers (formatting, sender mapping) plus the async orchestration that
fetches + parses + posts. No browser work lives here.
"""
from __future__ import annotations

import logging

from triage.parser_agent.claude import extract_steps
from triage.parser_agent.github import fetch_issue
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


async def post_initial_steps(
    cfg,
    *,
    anthropic_client,
    http_client,
    agent,
    issue_cache: dict,
) -> None:
    """Fetch the configured issue, parse it, and post the steps @ReproAgent."""
    issue = await fetch_issue(cfg.github_issue_url, http_client=http_client)
    issue_cache["issue"] = issue
    payload = await extract_steps(issue, client=anthropic_client)
    text = format_steps_message(payload)
    logger.info("[ParserAgent] posting %d steps @ReproAgent", len(payload.steps))
    await agent.send_message(["ReproAgent"], text)


def make_on_message(cfg, *, anthropic_client, http_client, issue_cache: dict):
    """Build the async on_message callback for ParserAgent.

    Reacts only to redirects from ReproAgent / HypothesisAgent (a message that
    @mentions ParserAgent to route work back). Re-parses the issue with their
    feedback woven in, and re-posts revised steps @ReproAgent. Self-messages and
    unknown senders are ignored.
    """

    async def on_message(payload, agent) -> None:
        sender = sender_agent_name(payload.sender_id, cfg)
        if sender not in ("ReproAgent", "HypothesisAgent"):
            logger.info(
                "[ParserAgent] ignoring message from %s (not a redirect)", sender
            )
            return

        redirect = payload.content
        logger.info("[ParserAgent] redirect from %s — re-parsing", sender)

        if issue_cache.get("issue") is None:
            issue_cache["issue"] = await fetch_issue(
                cfg.github_issue_url, http_client=http_client
            )
        payload_out = await extract_steps(
            issue_cache["issue"], client=anthropic_client, redirect=redirect
        )
        await agent.send_message(["ReproAgent"], format_steps_message(payload_out))

    return on_message
