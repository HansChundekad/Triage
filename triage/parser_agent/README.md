# ParserAgent

Posts structured repro steps into the Band room, @mentioning ReproAgent. A
failed repro can route back here for re-parsing.

## Phase 3 — echo only

No GitHub fetch, no Claude, no real parsing (that is Phase 5). On startup it:

1. Connects to Band as the `BAND_PARSER_*` identity.
2. Joins the shared room via `BAND_ROOM_ID` (or creates one if unset, then adds
   ReproAgent + HypothesisAgent so the room is usable by the other worktrees).
3. Posts ONE hardcoded message @mentioning ReproAgent:
   `@ReproAgent extracted 4 steps: focus input, type task, click add, click delete (issue: ...)`.
4. Listens forever; logs every message it receives and acks any sender that
   @mentions it. Prints everything it sends and receives.

**Room provisioning:** joining an existing `BAND_ROOM_ID` requires ParserAgent
to already be a participant of that room (Band rejects the WebSocket
subscription otherwise — see `docs/STATUS.md`). The Phase 2 room already has
ParserAgent added.

## Run

```bash
source .venv/bin/activate
python -m triage.parser_agent
```

Three-way coordination is proven by running this alongside the `triage-repro`
and `triage-hypothesis` worktrees against the same `BAND_ROOM_ID`.
