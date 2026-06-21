"""ReproAgent — Phase 3 echo (placeholder for Phase-4 browser execution).

NO browser here. This stands in for the real Browserbase/Stagehand work that
will live in this package in Phase 4. For now ReproAgent joins the shared Band
room, logs repro steps it receives from ParserAgent, and posts ONE hardcoded
fake repro result @mentioning HypothesisAgent — to prove three-way coordination.
"""
from __future__ import annotations

from triage.shared.band import ReproResultPayload

# Literal Band handle for the @mention target (matches triage/shared/band.py).
_HYPOTHESIS_HANDLE = "@hanschundekad/hypothesisagent"


def build_fake_result() -> ReproResultPayload:
    """Hardcoded placeholder result. Phase 4 replaces this with real browser evidence."""
    return ReproResultPayload(
        success=True,  # placeholder: we "reproduced" the reported bug
        evidence=[
            "Ran all 4 repro steps in PLACEHOLDER mode (no real browser yet — Phase 4).",
            "After deleting the last todo item, the app rendered a blank screen.",
        ],
        console_errors=[
            "TypeError: Cannot read properties of undefined (reading 'length') "
            "— empty array access after delete",
        ],
        session_url="https://www.browserbase.com/sessions/PLACEHOLDER-phase4-not-real-yet",
    )


def format_result_message(result: ReproResultPayload) -> str:
    """Render a directed @HypothesisAgent message from a ReproResultPayload."""
    verdict = "BUG REPRODUCED" if result.success else "BUG NOT REPRODUCED"
    lines = [
        f"{_HYPOTHESIS_HANDLE} repro result (Phase 3 echo — placeholder, no real browser):",
        f"verdict: {verdict}",
        "evidence:",
        *[f"  - {e}" for e in result.evidence],
        "console_errors:",
        *[f"  - {c}" for c in result.console_errors],
        f"session_url: {result.session_url}",
    ]
    return "\n".join(lines)


def _sender_is_hypothesis(sender_name: str | None) -> bool:
    """True if a message came from HypothesisAgent (so we don't echo its replies)."""
    return bool(sender_name and "hypothesis" in sender_name.lower())


import asyncio
import logging

from triage.config import load_config
from triage.shared.band import BandAgent

logger = logging.getLogger(__name__)


async def handle_parser_message(payload, agent) -> None:
    """on_message callback: log received steps, then echo ONE fake result @HypothesisAgent."""
    sender = getattr(payload, "sender_name", None)
    print(f"\n[ReproAgent] << received from {sender}:")
    print(f"    {payload.content!r}")

    if _sender_is_hypothesis(sender):
        print("[ReproAgent] sender is HypothesisAgent — ignoring (Phase 3 echo has no retry logic).")
        return

    print("[ReproAgent] logging repro steps (placeholder — real browser execution is Phase 4):")
    print(f"    {payload.content}")

    # events = logs (mirrors what real per-step browser logging will look like in Phase 4)
    await agent.send_event(
        "Executed repro steps in PLACEHOLDER mode (Phase 3 echo — no real browser).",
        "task",
    )

    text = format_result_message(build_fake_result())
    print("[ReproAgent] >> sending fake repro result @HypothesisAgent:")
    print(text)
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

    # Best-effort: make sure our echo target can actually receive it. ReproAgent
    # proved it can add participants in Phase 2. May no-op if already a member or
    # if ReproAgent does not own this room — log and continue either way.
    try:
        await agent.add_participant("HypothesisAgent")
        print("[ReproAgent] ensured HypothesisAgent is a room participant.")
    except Exception as exc:  # noqa: BLE001 — defensive, non-fatal
        print(f"[ReproAgent] could not add HypothesisAgent (may already be a member): {exc}")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await agent.disconnect()
        print("[ReproAgent] disconnected.")
