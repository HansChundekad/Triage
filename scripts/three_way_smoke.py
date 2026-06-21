#!/usr/bin/env python
"""Phase 3 proof: ParserAgent → ReproAgent (echo) → HypothesisAgent, all three live.

Throwaway verification harness (mirrors Phase 2 scripts/handshake.py). The stub
ParserAgent/HypothesisAgent here are test doubles ONLY — the real ones are built
in their own worktrees and integrate on main. This drives the REAL ReproAgent
echo handler so the three-way @mention routing is proven from this worktree.

Run:
    cp /Users/hanschundekad/Triage/.env /Users/hanschundekad/triage-repro/.env  # if missing
    .venv/bin/python scripts/three_way_smoke.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from triage.repro_agent.echo import handle_parser_message
from triage.shared.band import BandAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

TIMEOUT = 30

_REQUIRED = (
    "BAND_PARSER_API_KEY", "BAND_PARSER_AGENT_ID",
    "BAND_REPRO_API_KEY", "BAND_REPRO_AGENT_ID",
    "BAND_HYPOTHESIS_API_KEY", "BAND_HYPOTHESIS_AGENT_ID",
)


async def main() -> int:
    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        print(f"[ERROR] Missing env vars: {', '.join(missing)}")
        print("        Copy /Users/hanschundekad/Triage/.env into this worktree.")
        return 1

    hypothesis_got = asyncio.Event()

    async def hypothesis_on_message(payload, agent: BandAgent) -> None:
        print(f"\n  [HypothesisAgent] << received from {payload.sender_name}:")
        print(f"      {payload.content!r}\n")
        hypothesis_got.set()

    repro = BandAgent(
        name="ReproAgent",
        agent_id=os.environ["BAND_REPRO_AGENT_ID"],
        api_key=os.environ["BAND_REPRO_API_KEY"],
        on_message=handle_parser_message,   # the REAL echo under test
    )
    parser = BandAgent(
        name="ParserAgent",
        agent_id=os.environ["BAND_PARSER_AGENT_ID"],
        api_key=os.environ["BAND_PARSER_API_KEY"],
    )
    hypothesis = BandAgent(
        name="HypothesisAgent",
        agent_id=os.environ["BAND_HYPOTHESIS_AGENT_ID"],
        api_key=os.environ["BAND_HYPOTHESIS_API_KEY"],
        on_message=hypothesis_on_message,
    )

    print("\n=== TRIAGE Phase 3 — Three-Way Band Coordination ===\n")

    # ReproAgent owns the room so it can admit both peers before they subscribe.
    print("[1/6] Connecting ReproAgent (creates room) ...")
    room_id = await repro.connect(room_id=None)
    print(f"[2/6] ReproAgent admitting ParserAgent + HypothesisAgent to {room_id} ...")
    await repro.add_participant("ParserAgent")
    await repro.add_participant("HypothesisAgent")

    print("[3/6] Connecting ParserAgent + HypothesisAgent ...")
    await parser.connect(room_id=room_id)
    await hypothesis.connect(room_id=room_id)
    await asyncio.sleep(1.5)  # let all three WebSockets stabilise

    print("[4/6] ParserAgent → @ReproAgent: repro steps ...")
    await parser.send_message(
        mentions=["ReproAgent"],
        text=(
            "@hanschundekad/reproagent repro steps for issue #1 — "
            "1. Open app  2. Add one todo  3. Delete it  4. observe screen"
        ),
    )

    print(f"[5/6] Waiting for HypothesisAgent to receive the echo (timeout {TIMEOUT}s) ...")
    try:
        await asyncio.wait_for(hypothesis_got.wait(), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        print("\n[FAIL] HypothesisAgent never received ReproAgent's echo.")
        await parser.disconnect(); await hypothesis.disconnect(); await repro.disconnect()
        return 1

    print("[6/6] === THREE-WAY COORDINATION COMPLETE ===")
    print(f"Room: {room_id}  — all three WebSockets alive, @mention routing works.\n")
    await parser.disconnect(); await hypothesis.disconnect(); await repro.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
