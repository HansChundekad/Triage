#!/usr/bin/env python
"""Phase 2 handshake proof: ParserAgent sends, ReproAgent replies.

Run:
    source .venv/bin/activate
    python scripts/handshake.py

Both agents connect via WebSocket to the same Band room.
ParserAgent sends a message @mentioning ReproAgent.
ReproAgent's subscription fires and replies @mentioning ParserAgent back.
Script exits once the reply lands (or after 30 s timeout).

If BAND_ROOM_ID is unset, a new room is created and its ID is printed —
copy it into .env as BAND_ROOM_ID to reuse it on subsequent runs.
"""
from __future__ import annotations

import asyncio
import logging
import sys

import os

from dotenv import load_dotenv

load_dotenv()

from triage.shared.band import BandAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

TIMEOUT = 30  # seconds before giving up

_REQUIRED = {
    "BAND_PARSER_API_KEY", "BAND_PARSER_AGENT_ID",
    "BAND_REPRO_API_KEY", "BAND_REPRO_AGENT_ID",
}


def _load_band_env() -> dict:
    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        print(f"[ERROR] Missing env vars: {', '.join(missing)}")
        print("        Copy .env.example → .env and fill in Band credentials.")
        sys.exit(1)
    return {k: os.environ[k] for k in _REQUIRED} | {
        "BAND_ROOM_ID": os.environ.get("BAND_ROOM_ID") or None,
    }


async def main() -> int:
    env = _load_band_env()
    reply_received: asyncio.Event = asyncio.Event()

    # ------------------------------------------------------------------
    # ReproAgent: listens and replies once
    # ------------------------------------------------------------------
    async def repro_on_message(payload, agent: BandAgent) -> None:
        print(f"\n  [{agent.name}] << received from {payload.sender_name}:")
        print(f"      {payload.content!r}")
        print(f"  [{agent.name}] >> replying to ParserAgent ...")
        await agent.send_message(
            mentions=["ParserAgent"],
            text=(
                "@hanschundekad/parseragent ACK — repro steps received. "
                "Starting browser session now."
            ),
        )
        print(f"  [{agent.name}] reply sent.\n")
        reply_received.set()

    repro = BandAgent(
        name="ReproAgent",
        agent_id=env["BAND_REPRO_AGENT_ID"],
        api_key=env["BAND_REPRO_API_KEY"],
        on_message=repro_on_message,
    )

    parser = BandAgent(
        name="ParserAgent",
        agent_id=env["BAND_PARSER_AGENT_ID"],
        api_key=env["BAND_PARSER_API_KEY"],
    )

    room_id = env["BAND_ROOM_ID"]

    print("\n=== TRIAGE Phase 2 — Two-Agent Band Handshake ===\n")

    # ReproAgent connects first and creates/joins the room.
    # Then it adds ParserAgent as a participant before ParserAgent subscribes —
    # Band's WebSocket rejects subscription unless the agent is a room member.
    print("[1/5] Connecting ReproAgent ...")
    room_id = await repro.connect(room_id=room_id)

    print(f"[2/5] ReproAgent adding ParserAgent to room {room_id} ...")
    await repro.add_participant("ParserAgent")

    print(f"[3/5] Connecting ParserAgent to room {room_id} ...")
    await parser.connect(room_id=room_id)

    # Brief pause for both WebSockets to stabilise
    await asyncio.sleep(1.5)

    print("[4/5] ParserAgent → @ReproAgent: sending repro steps ...")
    await parser.send_message(
        mentions=["ReproAgent"],
        text=(
            "@hanschundekad/reproagent Repro steps for issue #42 — "
            "1. Open app  "
            "2. Add one todo item  "
            "3. Delete it  "
            "→ expected: empty state shown  "
            "→ actual: blank screen + TypeError in console"
        ),
    )

    print(f"[5/5] Waiting for ReproAgent reply (timeout {TIMEOUT}s) ...")
    try:
        await asyncio.wait_for(reply_received.wait(), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        print("\n[FAIL] Timed out — ReproAgent did not reply within the window.")
        print("       Check Band credentials and room membership.")
        await parser.disconnect()
        await repro.disconnect()
        return 1

    print("=== HANDSHAKE COMPLETE ===")
    print(f"Room: {room_id}")
    print("Both WebSockets stayed alive. @mention routing works.\n")

    await parser.disconnect()
    await repro.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
