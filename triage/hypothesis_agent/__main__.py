"""Run the HypothesisAgent as a long-lived process.

    .venv/bin/python -m triage.hypothesis_agent

Connects to the shared Band room (BAND_ROOM_ID) as the HypothesisAgent
identity and listens forever, echoing a placeholder diagnosis whenever
ReproAgent @mentions it. Ctrl-C to stop.
"""
from __future__ import annotations

import asyncio
import logging

from dotenv import load_dotenv

load_dotenv()

from triage.hypothesis_agent.agent import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[HypothesisAgent] stopped.")


if __name__ == "__main__":
    main()
