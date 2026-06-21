#!/usr/bin/env python
"""Runnable ParserAgent (Phase 5 — real GitHub fetch + Claude parsing).

Connects to Band as the BAND_PARSER_* identity, joins the shared room
(BAND_ROOM_ID), fetches the live GitHub issue, uses Claude to extract structured
repro steps (inferring unstated preconditions), and posts them @ReproAgent.
Then listens — re-parsing and re-posting whenever ReproAgent/HypothesisAgent
routes work back with a redirect.

Run:
    source .venv/bin/activate
    python -m triage.parser_agent
"""
from __future__ import annotations

import asyncio
import logging
import sys

import anthropic
import httpx

from triage.config import load_config
from triage.parser_agent.agent import make_on_message, post_initial_steps
from triage.shared.band import BandAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

STARTUP_DELAY = 2.0  # let the WebSocket settle before the first post


async def main() -> int:
    cfg = load_config()

    anthropic_client = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)
    http_client = httpx.AsyncClient()
    issue_cache: dict = {"issue": None}

    agent = BandAgent(
        name="ParserAgent",
        agent_id=cfg.band_parser.agent_id,
        api_key=cfg.band_parser.api_key,
        on_message=make_on_message(
            cfg,
            anthropic_client=anthropic_client,
            http_client=http_client,
            issue_cache=issue_cache,
        ),
    )

    print("\n=== TRIAGE Phase 5 — ParserAgent (real) ===\n")

    room_id = await agent.connect(room_id=cfg.band_room_id)
    print(f"[ParserAgent] connected to room {room_id}")

    # Solo bootstrap convenience: if we just created the room (no BAND_ROOM_ID),
    # add the other two so the room is immediately usable by their worktrees.
    if cfg.band_room_id is None:
        await agent.add_participant("ReproAgent")
        await agent.add_participant("HypothesisAgent")
        print(
            f"[ParserAgent] created room {room_id} and added ReproAgent + "
            f"HypothesisAgent — set BAND_ROOM_ID={room_id} for the other worktrees"
        )

    # Event = log (no @mention). Message = directed talk (below).
    await agent.send_event("ParserAgent online (real parsing)", "task")

    await asyncio.sleep(STARTUP_DELAY)

    print(f"[ParserAgent] fetching + parsing issue: {cfg.github_issue_url}")
    await post_initial_steps(
        cfg,
        anthropic_client=anthropic_client,
        http_client=http_client,
        agent=agent,
        issue_cache=issue_cache,
    )
    print("[ParserAgent] posted steps @ReproAgent.")

    print("[ParserAgent] listening — Ctrl-C to exit ...\n")
    try:
        await asyncio.Event().wait()  # run indefinitely on the WebSocket
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await agent.disconnect()
        await http_client.aclose()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n[ParserAgent] interrupted — shutting down.")
        sys.exit(0)
