"""Shared Band coordination layer for ParserAgent, ReproAgent, HypothesisAgent.

Every agent imports from here. BandAgent wraps BandLink so each of the three
identities connects with its own credentials while sharing one interface.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Coroutine, Literal

if TYPE_CHECKING:
    from band.platform.event import MessageCreatedPayload

logger = logging.getLogger(__name__)

AgentName = Literal["ParserAgent", "ReproAgent", "HypothesisAgent"]

# Known Band identities — set at registration time, stable for the project.
_AGENT_IDS: dict[str, str] = {
    "ParserAgent": "7b63179e-025d-4426-b403-6bd2da4d23d2",
    "ReproAgent": "40ceca32-dcc4-493d-991c-246101d3b1e0",
    "HypothesisAgent": "1c92f15a-1ece-4d41-9af4-f476cf4dadd5",
}

_AGENT_HANDLES: dict[str, str] = {
    "ParserAgent": "hanschundekad/parseragent",
    "ReproAgent": "hanschundekad/reproagent",
    "HypothesisAgent": "hanschundekad/hypothesisagent",
}


# ---------------------------------------------------------------------------
# Structured message payloads — the contract between agents
# ---------------------------------------------------------------------------

@dataclass
class ReproStepsPayload:
    """ParserAgent → ReproAgent: structured repro steps from a GitHub issue."""

    issue_url: str
    steps: list[str] = field(default_factory=list)


@dataclass
class ReproResultPayload:
    """ReproAgent → HypothesisAgent: evidence from one repro attempt."""

    success: bool
    evidence: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    session_url: str = ""


@dataclass
class HypothesisPayload:
    """HypothesisAgent → ReproAgent (redirect) or ParserAgent (done)."""

    root_cause: str
    redirect: str | None = None  # non-None means "retry with this tweak"


# ---------------------------------------------------------------------------
# BandAgent — one instance per agent identity
# ---------------------------------------------------------------------------

MessageCallback = Callable[
    ["MessageCreatedPayload", "BandAgent"],
    Coroutine,
]


class BandAgent:
    """One Band agent identity wrapping a BandLink WebSocket connection.

    Usage::

        agent = BandAgent("ParserAgent", agent_id="...", api_key="...")
        room_id = await agent.connect(room_id="existing-id-or-None")
        await agent.send_message(["ReproAgent"], "hello @reproagent ...")
        await agent.disconnect()
    """

    def __init__(
        self,
        name: AgentName,
        agent_id: str,
        api_key: str,
        on_message: MessageCallback | None = None,
    ) -> None:
        self.name = name
        self.handle = _AGENT_HANDLES[name]
        self._agent_id = agent_id
        self._api_key = api_key
        self._on_message = on_message
        self._link = None
        self._room_id: str | None = None
        self._listen_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, room_id: str | None = None) -> str:
        """Connect WebSocket and join/create a room. Returns room_id."""
        from band.platform.link import BandLink
        from band.client.rest import ChatRoomRequest, DEFAULT_REQUEST_OPTIONS

        self._link = BandLink(agent_id=self._agent_id, api_key=self._api_key)
        await self._link.connect()
        await self._link.subscribe_agent_rooms(self._agent_id)

        if room_id:
            self._room_id = room_id
        else:
            response = await self._link.rest.agent_api_chats.create_agent_chat(
                chat=ChatRoomRequest(),
                request_options=DEFAULT_REQUEST_OPTIONS,
            )
            self._room_id = response.data.id
            print(f"[{self.name}] Created room: {self._room_id}  ← set BAND_ROOM_ID={self._room_id}")

        await self._link.subscribe_room(self._room_id)
        logger.info("[%s] connected to room %s", self.name, self._room_id)

        if self._on_message:
            self._listen_task = asyncio.create_task(
                self._listen(), name=f"{self.name}-listener"
            )

        return self._room_id

    async def disconnect(self) -> None:
        """Stop listener and close WebSocket."""
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._link:
            await self._link.disconnect()
            self._link = None
        logger.info("[%s] disconnected", self.name)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def add_participant(self, name: AgentName) -> None:
        """Add another agent as a participant in this room."""
        if self._link is None or self._room_id is None:
            raise RuntimeError(f"[{self.name}] call connect() before add_participant()")

        from band.client.rest import ParticipantRequest, DEFAULT_REQUEST_OPTIONS

        await self._link.rest.agent_api_participants.add_agent_chat_participant(
            chat_id=self._room_id,
            participant=ParticipantRequest(
                participant_id=_AGENT_IDS[name],
                role="member",
            ),
            request_options=DEFAULT_REQUEST_OPTIONS,
        )
        logger.info("[%s] added %s to room %s", self.name, name, self._room_id)

    async def send_message(self, mentions: list[AgentName], text: str) -> None:
        """Send a directed message. At least one mention is required."""
        if not mentions:
            raise ValueError(f"[{self.name}] send_message requires at least one mention")
        if self._link is None or self._room_id is None:
            raise RuntimeError(f"[{self.name}] call connect() before send_message()")

        from band.client.rest import (
            ChatMessageRequest,
            ChatMessageRequestMentionsItem,
            DEFAULT_REQUEST_OPTIONS,
        )

        mention_items = [
            ChatMessageRequestMentionsItem(
                id=_AGENT_IDS[m],
                handle=_AGENT_HANDLES[m],
            )
            for m in mentions
        ]

        await self._link.rest.agent_api_messages.create_agent_chat_message(
            chat_id=self._room_id,
            message=ChatMessageRequest(content=text, mentions=mention_items),
            request_options=DEFAULT_REQUEST_OPTIONS,
        )
        logger.info("[%s] → %s: %s", self.name, mentions, text[:80])

    async def send_event(
        self,
        content: str,
        event_type: Literal["thought", "error", "task"],
        metadata: dict | None = None,
    ) -> None:
        """Post a structured event (no @mention needed — informational log)."""
        if self._link is None or self._room_id is None:
            raise RuntimeError(f"[{self.name}] call connect() before send_event()")

        from band.client.rest import ChatEventRequest, DEFAULT_REQUEST_OPTIONS

        await self._link.rest.agent_api_events.create_agent_chat_event(
            chat_id=self._room_id,
            event=ChatEventRequest(
                content=content,
                message_type=event_type,
                metadata=metadata,
            ),
            request_options=DEFAULT_REQUEST_OPTIONS,
        )
        logger.info("[%s] event(%s): %s", self.name, event_type, content[:80])

    # ------------------------------------------------------------------
    # Internal listener
    # ------------------------------------------------------------------

    async def _listen(self) -> None:
        """Consume WebSocket events and fire on_message for directed messages."""
        from band.platform.event import MessageEvent

        assert self._link is not None
        assert self._on_message is not None

        try:
            async for event in self._link:
                if isinstance(event, MessageEvent):
                    payload = event.payload
                    # Only react to messages in our room (ignore other subscriptions)
                    if payload.chat_room_id and payload.chat_room_id != self._room_id:
                        continue
                    # Ignore messages we sent ourselves
                    if payload.sender_id == self._agent_id:
                        continue
                    logger.info(
                        "[%s] received message from %s: %s",
                        self.name,
                        payload.sender_name,
                        payload.content[:80],
                    )
                    await self._on_message(payload, self)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("[%s] listener error: %s", self.name, exc)
            raise
