"""HypothesisAgent — Phase 3 echo-only.

Connects to the shared Band room as the HypothesisAgent identity, listens on
its WebSocket, and on a message @mentioning it from ReproAgent posts ONE
hardcoded placeholder diagnosis back @mentioning ReproAgent.

NO real Claude reasoning yet — the placeholder stands in for the real
root-cause analysis arriving in Phase 5. All Band logic is reused from
triage.shared.band; nothing here reimplements or modifies it.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine

from triage.config import Config, load_config
from triage.shared.band import BandAgent, HypothesisPayload

logger = logging.getLogger(__name__)

# Hardcoded stand-in for the Phase 5 Claude diagnosis. The fixed root cause
# matches TRIAGE's planted bug (blank screen + TypeError after deleting the
# last item). redirect=None means "no retry needed" — a plain acknowledgment.
PLACEHOLDER_HYPOTHESIS = HypothesisPayload(
    root_cause="reading items[0] after delete (empty-array dereference)",
    redirect=None,
)


def _format_hypothesis(h: HypothesisPayload) -> str:
    """Render a HypothesisPayload as the message text sent to ReproAgent.

    The structured mention (routing) is supplied separately via
    BandAgent.send_message(mentions=["ReproAgent"], ...); the leading handle
    here is for a readable room transcript, matching the Phase 2 convention.
    """
    text = (
        "@hanschundekad/reproagent confirmed, matches the report. "
        f"Root cause: {h.root_cause}. Repro valid."
    )
    if h.redirect:
        text += f" Redirect: {h.redirect}"
    return text


def make_echo_callback(
    repro_agent_id: str,
) -> Callable[[object, BandAgent], Coroutine]:
    """Build the on_message callback.

    Echoes PLACEHOLDER_HYPOTHESIS back to ReproAgent, but only for messages
    actually sent by ReproAgent (identified by sender_id). Everything sent and
    received is printed so @mention routing is watchable.
    """

    async def on_message(payload, agent: BandAgent) -> None:
        print(f"\n  [{agent.name}] << received from {payload.sender_name} ({payload.sender_id}):")
        print(f"      {payload.content!r}")

        if payload.sender_id != repro_agent_id:
            print(f"  [{agent.name}] (ignoring — sender is not ReproAgent)\n")
            return

        # Evidence logged. In Phase 5, real Claude reasoning replaces the line below.
        print(f"  [{agent.name}] evidence logged — posting placeholder diagnosis (Phase 5 reasons here).")
        text = _format_hypothesis(PLACEHOLDER_HYPOTHESIS)
        await agent.send_message(mentions=["ReproAgent"], text=text)
        print(f"  [{agent.name}] >> sent to ReproAgent: {text!r}\n")

    return on_message


async def run(cfg: Config | None = None) -> None:
    """Connect HypothesisAgent to the shared room and listen indefinitely.

    Precondition: HypothesisAgent must already be a participant in
    cfg.band_room_id (the room creator adds it — see scripts/hypothesis_echo_demo.py
    or, in the full system, ReproAgent/the orchestrator).
    """
    cfg = cfg or load_config()
    agent = BandAgent(
        name="HypothesisAgent",
        agent_id=cfg.band_hypothesis.agent_id,
        api_key=cfg.band_hypothesis.api_key,
        on_message=make_echo_callback(cfg.band_repro.agent_id),
    )
    room_id = await agent.connect(room_id=cfg.band_room_id)
    print(
        f"[HypothesisAgent] listening in room {room_id} — "
        "waiting for ReproAgent @mentions. Ctrl-C to stop."
    )
    try:
        await asyncio.Event().wait()  # stay alive forever
    finally:
        await agent.disconnect()
