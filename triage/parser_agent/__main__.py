#!/usr/bin/env python
"""Runnable ParserAgent (Phase 3 — echo only).

Connects to Band as the BAND_PARSER_* identity, joins the shared room
(BAND_ROOM_ID), posts ONE hardcoded structured-steps message @mentioning
ReproAgent, then listens forever — printing every message it sends and
receives, and acking any message that @mentions it.

Run:
    source .venv/bin/activate
    python -m triage.parser_agent
"""
from __future__ import annotations

import asyncio
import logging
import sys

from triage.config import load_config
from triage.parser_agent.echo import (
    build_repro_steps_payload,
    format_steps_message,
    make_on_message,
)
from triage.shared.band import BandAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

STARTUP_DELAY = 2.0  # let the WebSocket settle before the first post


async def main() -> int:
    cfg = load_config()

    agent = BandAgent(
        name="ParserAgent",
        agent_id=cfg.band_parser.agent_id,
        api_key=cfg.band_parser.api_key,
        on_message=make_on_message(cfg),
    )

    print("\n=== TRIAGE Phase 3 — ParserAgent (echo) ===\n")

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
    await agent.send_event("ParserAgent online (echo mode)", "task")

    await asyncio.sleep(STARTUP_DELAY)

    payload = build_repro_steps_payload(cfg.github_issue_url)
    text = format_steps_message(payload)
    print(f"[ParserAgent] >> @ReproAgent: {text!r}")
    await agent.send_message(["ReproAgent"], text)

    print("[ParserAgent] listening — Ctrl-C to exit ...\n")
    try:
        await asyncio.Event().wait()  # run indefinitely on the WebSocket
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await agent.disconnect()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n[ParserAgent] interrupted — shutting down.")
        sys.exit(0)
