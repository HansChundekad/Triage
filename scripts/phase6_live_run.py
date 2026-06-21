#!/usr/bin/env python
"""Phase 6 live end-to-end run — the real retry loop, all three real agents.

Composes the REAL callbacks in one process (no test doubles):
  - ParserAgent : real GitHub fetch + Claude -> structured steps
  - ReproAgent  : real Browserbase/Stagehand browser + retry loop
  - HypothesisAgent : real Claude root-cause + confirm/redirect routing

Order mirrors scripts/three_way_smoke.py so all listeners are subscribed
before ParserAgent posts. The ReproAgent's ReproLoopState is created here and
passed in, so we can watch state.terminal and exit cleanly when the loop
reaches a terminal state (bug confirmed, or could-not-reproduce after N).

Run:
    .venv/bin/python scripts/phase6_live_run.py
    .venv/bin/python scripts/phase6_live_run.py --force-retry

--force-retry posts a deliberately INCOMPLETE first step set (delete-only, no
add) so the live loop has to recover for real: empty app -> no crash ->
HypothesisAgent routes back to ParserAgent (redirect_parser) -> Parser
re-parses WITH the add steps -> a fresh Browserbase session reproduces the
bug. Nothing in detection is faked — the fail->succeed flip is genuine. The
production agents are untouched; this scaffolding lives only in the harness.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time

import anthropic
import httpx
from dotenv import load_dotenv

load_dotenv()

from triage.config import load_config
from triage.hypothesis_agent.agent import make_diagnosis_callback
from triage.parser_agent.agent import format_steps_message, make_on_message, post_initial_steps
from triage.parser_agent.github import fetch_issue
from triage.repro_agent.echo import make_repro_callback
from triage.repro_agent.loop import ReproLoopState
from triage.shared.band import BandAgent, ReproStepsPayload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

# A live attempt drives a real cloud browser (~30-90s) + Claude calls. Cap the
# whole run so a hang can never wedge the harness.
WALL_CLOCK_TIMEOUT = 600  # seconds
STABILISE = 2.0

# Deliberately INCOMPLETE first steps for --force-retry: delete-only, no add.
# On the empty app these find nothing to delete -> no crash -> a genuine
# BUG NOT REPRODUCED, which HypothesisAgent should route to redirect_parser.
_FORCED_BROKEN_STEPS = [
    "Click the Delete button on the first task in the list",
    "Click the 'Yes, delete' confirmation button to confirm the deletion",
    "Click the Delete button on the next remaining task in the list",
    "Click the 'Yes, delete' confirmation button to confirm the deletion",
]


async def main(force_retry: bool = False) -> int:
    cfg = load_config()

    # Real clients (mirrors each agent's own __main__).
    parser_anthropic = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key)
    hypothesis_anthropic = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    http_client = httpx.AsyncClient()
    issue_cache: dict = {"issue": None}

    # ReproAgent's loop state lives here so we can detect terminal + summarise.
    repro_state = ReproLoopState()

    repro = BandAgent(
        name="ReproAgent",
        agent_id=cfg.band_repro.agent_id,
        api_key=cfg.band_repro.api_key,
        on_message=make_repro_callback(cfg, repro_state),
    )
    parser = BandAgent(
        name="ParserAgent",
        agent_id=cfg.band_parser.agent_id,
        api_key=cfg.band_parser.api_key,
        on_message=make_on_message(
            cfg,
            anthropic_client=parser_anthropic,
            http_client=http_client,
            issue_cache=issue_cache,
        ),
    )
    hypothesis = BandAgent(
        name="HypothesisAgent",
        agent_id=cfg.band_hypothesis.agent_id,
        api_key=cfg.band_hypothesis.api_key,
        on_message=make_diagnosis_callback(hypothesis_anthropic, cfg.band_repro.agent_id),
    )

    print("\n=== TRIAGE Phase 6 — Live Retry Loop (all real) ===\n")
    print(f"app:   {cfg.app_url}")
    print(f"issue: {cfg.github_issue_url}\n")

    # ReproAgent owns the room so it can admit both peers before they subscribe.
    print("[1/5] ReproAgent connecting (creates room) ...")
    room_id = await repro.connect(room_id=cfg.band_room_id)
    if cfg.band_room_id is None:
        await repro.add_participant("ParserAgent")
        await repro.add_participant("HypothesisAgent")
    print(f"[2/5] Room: {room_id}")

    print("[3/5] ParserAgent + HypothesisAgent connecting ...")
    await parser.connect(room_id=room_id)
    await hypothesis.connect(room_id=room_id)
    await asyncio.sleep(STABILISE)

    if force_retry:
        print("[4/5] FORCE-RETRY: posting deliberately INCOMPLETE (delete-only) "
              "steps @ReproAgent — the loop must recover via redirect_parser ...")
        # Warm the issue cache so ParserAgent's re-parse (on redirect_parser)
        # reuses the same issue instead of re-fetching.
        issue_cache["issue"] = await fetch_issue(cfg.github_issue_url, http_client=http_client)
        broken = ReproStepsPayload(issue_url=cfg.github_issue_url, steps=_FORCED_BROKEN_STEPS)
        await parser.send_message(["ReproAgent"], format_steps_message(broken))
    else:
        print("[4/5] ParserAgent fetching + parsing issue, posting @ReproAgent ...")
        await post_initial_steps(
            cfg,
            anthropic_client=parser_anthropic,
            http_client=http_client,
            agent=parser,
            issue_cache=issue_cache,
        )

    print(f"[5/5] Running loop — waiting for terminal (timeout {WALL_CLOCK_TIMEOUT}s) ...\n")
    deadline = time.monotonic() + WALL_CLOCK_TIMEOUT
    while not repro_state.terminal and time.monotonic() < deadline:
        await asyncio.sleep(1)

    print("\n=== RUN SUMMARY ===")
    print(f"terminal:      {repro_state.terminal}")
    print(f"attempts:      {repro_state.attempts}/{repro_state.max_attempts}")
    print(f"session URLs:  {len(repro_state.session_urls)}")
    for i, url in enumerate(repro_state.session_urls, 1):
        print(f"  attempt {i}: {url}")
    if not repro_state.terminal:
        print("WARNING: hit wall-clock timeout before a terminal state.")

    await parser.disconnect()
    await hypothesis.disconnect()
    await repro.disconnect()
    await http_client.aclose()
    return 0 if repro_state.terminal else 1


if __name__ == "__main__":
    force = "--force-retry" in sys.argv[1:]
    try:
        sys.exit(asyncio.run(main(force_retry=force)))
    except KeyboardInterrupt:
        print("\n[phase6_live_run] interrupted.")
        sys.exit(0)
