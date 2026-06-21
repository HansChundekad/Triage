# triage/hypothesis_agent/agent.py
"""HypothesisAgent — Phase 5: real Claude reasoning.

When @mentioned by ReproAgent with evidence (verdict, session URL, step
evidence, console errors), reason about root cause with Claude and either:
  - confirm the repro (@ReproAgent), or
  - redirect ReproAgent to retry with a tweak (@ReproAgent), or
  - redirect ParserAgent to re-parse the issue (@ParserAgent).

Band wiring (connect / listener / disconnect) is reused unchanged from
triage.shared.band — nothing here reimplements or modifies it. The redirect
TARGET is decided in this layer; the shared HypothesisPayload(root_cause,
redirect) schema is conformed to as-is.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine

import anthropic

from triage.config import Config, load_config
from triage.hypothesis_agent.reasoning import MODEL, Diagnosis, diagnose
from triage.shared.band import AgentName, BandAgent, HypothesisPayload
from triage.tracing.run_context import NullRunTrace

logger = logging.getLogger(__name__)

# Cosmetic transcript handles (structured @mention routing is supplied
# separately via BandAgent.send_message(mentions=[...]); these mirror the
# Phase 2/3 convention for a readable room transcript).
_HANDLES: dict[AgentName, str] = {
    "ReproAgent": "@hanschundekad/reproagent",
    "ParserAgent": "@hanschundekad/parseragent",
}


def route_diagnosis(d: Diagnosis) -> tuple[list[AgentName], HypothesisPayload]:
    """Map a Diagnosis to (Band @mention targets, shared HypothesisPayload).

    confirm        → @ReproAgent, redirect=None
    redirect_repro → @ReproAgent, redirect=instruction
    redirect_parser→ @ParserAgent, redirect=instruction
    """
    if d.decision == "redirect_parser":
        target: AgentName = "ParserAgent"
    else:
        target = "ReproAgent"

    redirect = None if d.decision == "confirm" else (d.redirect_instruction or None)
    payload = HypothesisPayload(root_cause=d.root_cause, redirect=redirect)
    return [target], payload


def format_diagnosis_message(target: AgentName, d: Diagnosis) -> str:
    """Render the directed message text for the chosen target."""
    handle = _HANDLES[target]
    if d.decision == "confirm":
        return (
            f"{handle} confirmed, matches the report. "
            f"Root cause: {d.root_cause}. Repro valid."
        )
    return f"{handle} {d.redirect_instruction} (suspected cause: {d.root_cause})"


def make_diagnosis_callback(
    client,
    repro_agent_id: str,
    model: str = MODEL,
    run_trace=None,
) -> Callable[[object, BandAgent], Coroutine]:
    """Build the on_message callback.

    Reacts only to messages from ReproAgent (by sender_id). Runs the blocking
    Claude diagnosis in a worker thread so the WebSocket loop is not stalled,
    then posts the diagnosis as a directed @mention. Everything is printed so
    @mention routing is watchable in the demo.
    """
    trace = run_trace if run_trace is not None else NullRunTrace()

    async def on_message(payload, agent: BandAgent) -> None:
        print(
            f"\n  [{agent.name}] << received from "
            f"{getattr(payload, 'sender_name', None)} "
            f"({getattr(payload, 'sender_id', None)}):"
        )
        print(f"      {payload.content!r}")

        if getattr(payload, "sender_id", None) != repro_agent_id:
            print(f"  [{agent.name}] (ignoring — sender is not ReproAgent)\n")
            return

        await agent.send_event("Diagnosing repro evidence with Claude", "thought")

        try:
            with trace.claude_span("hypothesis_generation"):
                diagnosis = await asyncio.to_thread(diagnose, payload.content, client, model)
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] diagnosis failed: %s", agent.name, exc)
            await agent.send_event(f"Diagnosis error: {exc}", "error")
            # Fail safe: ask ReproAgent to retry rather than going silent.
            await agent.send_message(
                ["ReproAgent"],
                f"{_HANDLES['ReproAgent']} diagnosis failed ({exc}); please retry.",
            )
            return

        mentions, _hyp_payload = route_diagnosis(diagnosis)
        text = format_diagnosis_message(mentions[0], diagnosis)
        await agent.send_event(
            f"Diagnosis: {diagnosis.decision} — {diagnosis.root_cause[:80]}", "thought"
        )
        await agent.send_message(mentions, text)
        print(f"  [{agent.name}] >> sent to {mentions}: {text!r}\n")

    return on_message


async def run(cfg: Config | None = None) -> None:
    """Connect HypothesisAgent to the shared room and listen indefinitely.

    Precondition: HypothesisAgent must already be a participant in
    cfg.band_room_id (the room creator / ReproAgent adds it). HypothesisAgent
    best-effort adds ParserAgent so the redirect_parser path can reach it.
    """
    cfg = cfg or load_config()
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    agent = BandAgent(
        name="HypothesisAgent",
        agent_id=cfg.band_hypothesis.agent_id,
        api_key=cfg.band_hypothesis.api_key,
        on_message=make_diagnosis_callback(client, cfg.band_repro.agent_id),
    )
    room_id = await agent.connect(room_id=cfg.band_room_id)

    try:
        await agent.add_participant("ParserAgent")
        print("[HypothesisAgent] ensured ParserAgent is a room participant.")
    except Exception as exc:  # noqa: BLE001
        print(f"[HypothesisAgent] could not add ParserAgent (may already be a member): {exc}")

    print(
        f"[HypothesisAgent] listening in room {room_id} — "
        "waiting for ReproAgent @mentions. Ctrl-C to stop."
    )
    try:
        await asyncio.Event().wait()  # stay alive forever
    finally:
        await agent.disconnect()
