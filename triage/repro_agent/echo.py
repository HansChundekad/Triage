"""ReproAgent — Phase 4: real Browserbase/Stagehand execution.

Receives ParserAgent's step list via Band @mention, runs a live Browserbase
session, and reports real evidence @HypothesisAgent.

Band wiring (Phase 3, unchanged):
  - on_message callback: handle_parser_message
  - run(): connect, add_participant, listen loop
"""
from __future__ import annotations

import asyncio
import logging

from triage.config import load_config
from triage.repro_agent.browser import run_repro
from triage.repro_agent.loop import parse_steps
from triage.shared.band import BandAgent, ReproResultPayload

logger = logging.getLogger(__name__)

_HYPOTHESIS_HANDLE = "@hanschundekad/hypothesisagent"


def format_result_message(result: ReproResultPayload) -> str:
    """Render a directed @HypothesisAgent message from a ReproResultPayload."""
    verdict = "BUG REPRODUCED" if result.success else "BUG NOT REPRODUCED"
    lines = [
        f"{_HYPOTHESIS_HANDLE} repro result:",
        f"verdict: {verdict}",
        f"session_url: {result.session_url}",
        "evidence:",
        *[f"  - {e}" for e in result.evidence],
        "console_errors:",
        *[f"  - {c}" for c in result.console_errors],
    ]
    return "\n".join(lines)


def _sender_is_hypothesis(sender_name: str | None) -> bool:
    return bool(sender_name and "hypothesis" in sender_name.lower())


async def handle_parser_message(payload, agent) -> None:
    """on_message callback: run real browser session and report @HypothesisAgent."""
    sender = getattr(payload, "sender_name", None)
    print(f"\n[ReproAgent] << received from {sender}:")
    print(f"    {payload.content!r}")

    if _sender_is_hypothesis(sender):
        print("[ReproAgent] sender is HypothesisAgent — ignoring (retry logic is Task 2).")
        return

    steps = parse_steps(payload.content)
    if not steps:
        print("[ReproAgent] no numbered steps in message — ignoring.")
        return

    print(f"[ReproAgent] parsed {len(steps)} steps — launching real Browserbase session…")
    cfg = load_config()

    await agent.send_event("Starting Browserbase repro session", "task")

    try:
        result = await run_repro(cfg, steps)
    except Exception as exc:  # noqa: BLE001
        logger.error("[ReproAgent] browser execution failed: %s", exc)
        await agent.send_event(f"Browser execution error: {exc}", "error")
        result = ReproResultPayload(
            success=False,
            evidence=[f"Execution error: {exc}"],
            console_errors=[],
            session_url="",
        )

    await agent.send_event(
        f"Repro complete — bug_detected={result.success}, "
        f"{len(result.console_errors)} console error(s)",
        "task",
    )

    text = format_result_message(result)
    print("[ReproAgent] >> sending real repro result @HypothesisAgent:")
    print(text[:500], "…" if len(text) > 500 else "")
    await agent.send_message(["HypothesisAgent"], text)
    print("[ReproAgent] sent.\n")


async def run() -> None:
    """Connect ReproAgent to the shared room and stay alive on its WebSocket."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = load_config()
    agent = BandAgent(
        name="ReproAgent",
        agent_id=cfg.band_repro.agent_id,
        api_key=cfg.band_repro.api_key,
        on_message=handle_parser_message,
    )

    room_id = await agent.connect(room_id=cfg.band_room_id)
    print(f"[ReproAgent] connected to room {room_id}. Listening for @mentions. Ctrl-C to stop.")

    try:
        await agent.add_participant("HypothesisAgent")
        print("[ReproAgent] ensured HypothesisAgent is a room participant.")
    except Exception as exc:  # noqa: BLE001
        print(f"[ReproAgent] could not add HypothesisAgent (may already be a member): {exc}")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await agent.disconnect()
        print("[ReproAgent] disconnected.")
