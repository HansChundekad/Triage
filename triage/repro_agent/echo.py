"""ReproAgent — Phase 4: real Browserbase/Stagehand execution.

Receives ParserAgent's step list via Band @mention, runs a live Browserbase
session, and reports real evidence @HypothesisAgent.

Band wiring (Phase 3, unchanged):
  - on_message callback: make_repro_callback (stateful retry loop, Phase 6)
  - run(): connect, add_participant, listen loop
"""
from __future__ import annotations

import asyncio
import logging

from triage.config import load_config
from triage.repro_agent.browser import run_repro
from triage.repro_agent.loop import (
    ReproLoopState,
    classify_message,
    extract_tweak,
    parse_steps,
)
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


def make_repro_callback(cfg, state: ReproLoopState | None = None):
    """Build the stateful on_message callback (one ReproLoopState per process).

    Mirrors hypothesis_agent.make_diagnosis_callback: a closure so retry state
    survives across messages. Routes by classify_message; all browser work is
    delegated to _run_attempt -> run_repro (fresh session each call).
    """
    state = state if state is not None else ReproLoopState()

    async def on_message(payload, agent) -> None:
        sender = getattr(payload, "sender_name", None)
        sender_id = getattr(payload, "sender_id", None)
        print(f"\n[ReproAgent] << from {sender}: {payload.content[:120]!r}")

        kind = classify_message(
            sender_id, payload.content,
            cfg.band_parser.agent_id, cfg.band_hypothesis.agent_id,
        )

        if kind == "steps":
            state.reset(parse_steps(payload.content))
            print(f"[ReproAgent] parsed {len(state.steps)} steps — starting cycle.")
            await _run_attempt(cfg, state, agent, tweak=None)

        elif kind == "redirect":
            if not state.steps or state.attempts_exhausted:
                # No cycle in progress, or cap reached — Task 3 finalizes the
                # terminal give-up message here. Minimal safe stop for now.
                print("[ReproAgent] redirect ignored (no steps or cap reached).")
                return
            tweak = extract_tweak(payload.content)
            await agent.send_event(
                f"Attempt {state.attempts} did not reproduce; HypothesisAgent "
                f"redirected — retrying with tweak: {tweak!r}",
                "task",
            )
            await _run_attempt(cfg, state, agent, tweak=tweak)

        elif kind == "confirm":
            # Task 3 latches terminal here.
            print("[ReproAgent] HypothesisAgent confirmed — cycle complete.")

        else:
            print(f"[ReproAgent] ignoring message (kind={kind}).")

    return on_message


async def _run_attempt(cfg, state: ReproLoopState, agent, tweak: str | None) -> None:
    """Run one browser attempt (fresh session) and post the result."""
    state.attempts += 1
    await agent.send_event(
        f"Starting Browserbase repro attempt {state.attempts}/{state.max_attempts}"
        + (f" (tweak: {tweak})" if tweak else ""),
        "task",
    )
    try:
        result = await run_repro(cfg, state.steps, tweak=tweak)
    except Exception as exc:  # noqa: BLE001
        logger.error("[ReproAgent] browser execution failed: %s", exc)
        await agent.send_event(f"Browser execution error: {exc}", "error")
        result = ReproResultPayload(
            success=False,
            evidence=[f"Execution error: {exc}"],
            console_errors=[],
            session_url="",
        )
    if result.session_url:
        state.session_urls.append(result.session_url)  # keep replay URL (Phase 7)
    await agent.send_event(
        f"Attempt {state.attempts} complete — bug_detected={result.success}, "
        f"{len(result.console_errors)} console error(s)",
        "task",
    )
    text = format_result_message(result)
    await agent.send_message(["HypothesisAgent"], text)
    print(f"[ReproAgent] >> attempt {state.attempts} result @HypothesisAgent sent.")


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
        on_message=make_repro_callback(cfg),
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
