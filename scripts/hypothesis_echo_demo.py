#!/usr/bin/env python
"""Phase 5 live proof: ReproAgent stand-in ↔ HypothesisAgent real Claude diagnosis.

Run:
    .venv/bin/python scripts/hypothesis_echo_demo.py

A ReproAgent stand-in (no browser — just sends one evidence message) and the
REAL HypothesisAgent echo callback both connect to the shared Band room. The
stand-in @mentions HypothesisAgent with evidence; HypothesisAgent logs it and
posts its placeholder diagnosis back @mentioning ReproAgent; the stand-in
receives that echo and the script exits. Two live WebSockets, @mention routing
both directions.

If BAND_ROOM_ID is unset, a new room is created and its ID printed — copy it
into .env to reuse it (and so all three agents share ONE room).
"""
from __future__ import annotations

import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv()

import anthropic

from triage.config import load_config
from triage.shared.band import BandAgent
from triage.hypothesis_agent.agent import make_diagnosis_callback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

TIMEOUT = 30  # seconds before giving up


async def main() -> int:
    cfg = load_config()
    echo_received: asyncio.Event = asyncio.Event()

    # ReproAgent stand-in: sends evidence, then listens for the echo back.
    async def repro_on_message(payload, agent: BandAgent) -> None:
        if payload.sender_id != cfg.band_hypothesis.agent_id:
            return  # only react to HypothesisAgent's echo
        print(f"\n  [{agent.name} stand-in] << echo from {payload.sender_name}:")
        print(f"      {payload.content!r}")
        echo_received.set()

    repro = BandAgent(
        name="ReproAgent",
        agent_id=cfg.band_repro.agent_id,
        api_key=cfg.band_repro.api_key,
        on_message=repro_on_message,
    )
    hypo_client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    hypo = BandAgent(
        name="HypothesisAgent",
        agent_id=cfg.band_hypothesis.agent_id,
        api_key=cfg.band_hypothesis.api_key,
        on_message=make_diagnosis_callback(hypo_client, cfg.band_repro.agent_id),
    )

    print("\n=== TRIAGE Phase 5 — HypothesisAgent Diagnosis Demo ===\n")

    # ReproAgent stand-in creates/joins the room and must add HypothesisAgent
    # as a participant BEFORE HypothesisAgent subscribes (Band requires it).
    print("[1/5] Connecting ReproAgent stand-in ...")
    room_id = await repro.connect(room_id=cfg.band_room_id)

    print(f"[2/5] Adding HypothesisAgent to room {room_id} ...")
    await repro.add_participant("HypothesisAgent")

    print(f"[3/5] Connecting HypothesisAgent to room {room_id} ...")
    await hypo.connect(room_id=room_id)

    await asyncio.sleep(1.5)  # let both WebSockets stabilise

    print("[4/5] ReproAgent → @HypothesisAgent: sending evidence ...")
    await repro.send_message(
        mentions=["HypothesisAgent"],
        text=(
            "@hanschundekad/hypothesisagent repro result:\n"
            "verdict: BUG REPRODUCED\n"
            "session_url: https://www.browserbase.com/sessions/demo\n"
            "evidence:\n"
            "  - focus input, type task, click add, click delete, confirm delete\n"
            "  - after confirming delete the app went blank (body text 8 chars)\n"
            "console_errors:\n"
            "  - TypeError: Cannot read properties of undefined (reading '0')"
        ),
    )

    print(f"[5/5] Waiting for HypothesisAgent echo (timeout {TIMEOUT}s) ...")
    try:
        await asyncio.wait_for(echo_received.wait(), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        print("\n[FAIL] Timed out — no echo from HypothesisAgent.")
        print("       Check Band credentials and room membership.")
        await hypo.disconnect()
        await repro.disconnect()
        return 1

    print("=== ECHO LOOP COMPLETE ===")
    print(f"Room: {room_id}")
    print("Two WebSockets stayed alive. @mention routing works both directions.\n")

    await hypo.disconnect()
    await repro.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
