# TRIAGE — Integration Guidance for Claude Code

> **What this file is.** Working reference for building TRIAGE's three integrations: **Browserbase** (real cloud browser), **Band** (multi-agent coordination), and **Arize Phoenix** (tracing). The connectivity details below are sourced from official docs and verified. Treat them as the baseline contract.
>
> **What this file is NOT.** A substitute for live documentation. SDKs and MCP surfaces drift. **Before you write integration code against any of these three services, do your own research to confirm the current method names, parameters, and auth flow.** Where this file and the live docs disagree, the live docs win — but tell me about the discrepancy rather than silently picking one.

---

## 0. How to use this document

1. **Read the relevant section fully before writing any code that touches that service.** Don't pattern-match a method name from memory.
2. **Verify against the live source.** Each service below lists how to reach its current docs (MCP doc server, package registry, or official site). Run that check first.
3. **Never invent connection patterns.** If something you need isn't in this doc and isn't in the live docs you fetched, stop and ask — do not improvise an endpoint, tool name, or auth header.
4. **Respect the architecture.** The system design is locked (see `TRIAGE_OVERVIEW.md`). This file is *how to connect*, not *what to build*. Don't redesign the agent topology.
5. **Flag drift.** If a confirmed detail here turns out wrong against live docs, surface it explicitly so we can update this file.

---

## 1. Project shape (so you know where integration code goes)

TRIAGE reproduces a reported bug by driving a real browser through a live app. Three agents coordinate in **one Band room**:

- **Issue Parser Agent** — fetches a GitHub issue, Claude turns vague prose into structured repro steps, posts them into the room @mentioning the Repro Agent.
- **Repro Agent** *(the hero — all Browserbase depth lives here)* — spins a real cloud browser, executes each step as a natural-language Stagehand action, screenshots every step, captures console errors, reports findings @mentioning the Hypothesis Agent.
- **Hypothesis Agent** — reads the evidence, diagnoses root cause, @mentions back a diagnosis, and can **redirect** ("@ReproAgent retry with a slower delete"). That redirect is the coordination loop.

**The one loop that earns three bounties:** a failed repro → Band redirect (coordination) → fresh Browserbase session + retry (real browser) → the whole fail→adjust→succeed progression shows in the Arize trace (it got smarter). When you touch the retry loop, you are touching all three integrations at once — be careful there.

**Concentration rules (do not violate):**
- **All** browser work stays in the Repro Agent. Do not spread Stagehand calls across agents.
- Agents only see messages they are **@mentioned** in. A message with no @mention reaches no one.
- **Never name an agent generically** ("Agent", "Bot", "Assistant", "AI"). Use `ReproAgent`, `HypothesisAgent`, `ParserAgent`. Generic names break @mention routing because the model treats them as roles, not names.

---

## 2. Browserbase + Stagehand

**Role in TRIAGE:** the real cloud browser that navigates to the app under test, executes repro steps in natural language, captures screenshots, and extracts console errors. This is the proof it's real automation, not scraping — so the browser must be *visibly real* (live session, streamable view).

**Verify current details before coding:**
- Browserbase MCP package: `@browserbasehq/mcp` (npm).
- Stagehand package: `stagehand` (TS-native; Python SDK also exists).
- Check the official Stagehand docs for the current `act()` / `observe()` / `extract()` signatures before relying on them — this surface evolves.

### 2.1 Two integration paths

- **MCP server** (recommended for Claude-based agents) — exposes browser control tools directly to the LLM.
- **Direct SDK** (TS or Python) — programmatic control. Use this inside the Repro Agent if you need tighter control over the session lifecycle and capture.

> Decide one path for the Repro Agent and stay consistent. Don't half-use MCP and half-use the SDK in the same agent.

### 2.2 MCP config block

```json
{
  "mcpServers": {
    "browserbase": {
      "command": "npx",
      "args": ["@browserbasehq/mcp", "--api-key", "YOUR_BROWSERBASE_API_KEY"]
    }
  }
}
```

### 2.3 MCP tools (exact names)

| Tool | Purpose | Key param |
|---|---|---|
| `browserbase_session_create` | Create/reuse a cloud session (Stagehand initialized) | `sessionId` (optional — omit to create new) |
| `browserbase_session_close` | Close session, cleanup | none |
| `browserbase_stagehand_navigate` | Go to a URL | `url` (required) |
| `browserbase_stagehand_act` | Natural-language action | `action` e.g. `"click the Submit button"` |
| `browserbase_stagehand_observe` | Find actionable elements | `instruction` e.g. `"find the login form"` |
| `browserbase_stagehand_extract` | Extract visible text (filters CSS/JS) | `instruction` (optional) |
| `browserbase_stagehand_get_url` | Current URL | none |
| `browserbase_screenshot` | PNG screenshot of current page | none — returns base64 PNG |

Screenshot resource URI: `screenshot://screenshot-name-of-the-screenshot`

### 2.4 Session lifecycle (one repro attempt)

1. `browserbase_session_create` → get `sessionId`
2. `browserbase_stagehand_navigate` → app URL
3. `browserbase_stagehand_observe` → **confirm elements exist before acting** (don't blind-fire actions)
4. `browserbase_stagehand_act` × N → each repro step
5. `browserbase_stagehand_extract` → pull error messages / state
6. `browserbase_screenshot` → capture evidence
7. `browserbase_session_close` → cleanup

> **Critical for the retry story:** create a **new session per retry** (`browserbase_session_create` with **no** `sessionId`). Clean browser state each retry, and a separate replay URL per attempt — which is exactly what makes the Arize progression legible.

### 2.5 Session replay

Every session gets a live-view URL: `https://www.browserbase.com/sessions/{sessionId}`
Embed this in the final report as evidence, and pre-open it for the live demo.

### 2.6 Env vars

```
BROWSERBASE_API_KEY=...
BROWSERBASE_PROJECT_ID=...
```

### 2.7 Bug-detection is the hard part — do not hand-wave it

Executing the steps is the easy 80%. **Correctly detecting whether the bug fired is the fiddly 20% that wins or loses the demo.** For TRIAGE's planted bug (blank screen + console TypeError on deleting the last item), detection should combine: (a) `extract` returning empty/blank body content, and (b) a captured console error matching the expected `Cannot read properties of undefined`. Don't rely on a single signal. Get this right before adding any second bug.

---

## 3. Band

**Role in TRIAGE:** the message bus between the three agents. Agents join a room, send messages via **@mentions**, and post structured events (tool calls, thoughts, errors, progress). Most traffic is agent-to-agent, no human in the loop.

**Verify current details before coding:**
- SDK package: `band-sdk` (check the registry for the current version and the exact `Agent.create` / adapter signatures).
- Confirm the Agent API base path and the WebSocket URL against live docs — auth flows change.

### 3.1 Two APIs — TRIAGE uses the Agent API only

| API | Base path | Who | Visibility |
|---|---|---|---|
| Human API | `/api/v1/me` | platform owner / setup | sees ALL room messages |
| Agent API | `/api/v1/agent` | TRIAGE agents at runtime | sees only @mentioned messages |

Human API needs an enterprise plan. **Stay on the Agent API.**

### 3.2 Agent API endpoints (exact paths)

| Endpoint | Method | Purpose |
|---|---|---|
| `/agent/me` | GET | validate connection / confirm identity |
| `/agent/peers` | GET | list recruitable agents |
| `/agent/chats` | GET | list chat rooms |
| `/agent/chats/{id}/participants` | POST | add a peer to a chat |
| `/agent/chats/{id}/participants` | GET | list room members |
| `/agent/chats/{id}/messages` | POST | send a message (**must @mention**) |
| `/agent/chats/{id}/events` | POST | post a structured event (tool call, thought, error, progress) |
| `/agent/chats/{id}/context` | GET | rehydrate state on reconnect |

Auth header: `X-API-Key: YOUR_AGENT_API_KEY` (created when registering a remote agent in the Band dashboard).

### 3.3 Messages vs. Events — do not confuse these

- **`POST /messages`** — directed text **with @mentions**. How agents talk to each other.
- **`POST /events`** — structured logs (tool calls, thoughts, errors, progress). Informational, NOT directed.

> Log every browser action, screenshot, and extraction as an **event**. Use **messages** only when one agent communicates a result to another via @mention. The retry-failure log is an **event**; the "retry with a tweak" redirect is a **message**.

### 3.4 Mention-based visibility

Agents see only messages where they're explicitly @mentioned — even if they're room participants. Route deliberately.

```
"@HypothesisAgent here are the repro results: ..."   → only HypothesisAgent sees it
"@ReproAgent retry with modified step 3"             → only ReproAgent sees it
"@ReproAgent @HypothesisAgent sync needed"           → both see it
```

### 3.5 SDK (strongly recommended — handles WebSocket)

```bash
pip install band-sdk
```

Without the SDK's WebSocket subscription, an agent can **send** but never **receive** — one-directional and useless for coordination. Use the SDK unless you have a strong reason not to.

SDK tools exposed to the LLM: `band_send_message`, `band_send_event`, `band_add_participant`, `band_remove_participant`, `band_get_participants`, `band_lookup_peers`, `band_create_chatroom`, `band_list_contacts`, `band_add_contact`.

Connection pattern:
```python
from band import Agent
from band.adapters import AnthropicAdapter  # or ClaudeSDKAdapter

adapter = AnthropicAdapter(...)            # wrap your Claude/Anthropic client
agent = Agent.create(adapter=adapter, agent_id="...", api_key="...")
await agent.run()                          # opens WebSocket, runs indefinitely
```

Confirmed adapters: `AnthropicAdapter`, `ClaudeSDKAdapter`, `LangGraphAdapter`, `PydanticAIAdapter`, `CrewAIAdapter`, `OpenAIAdapter`, `GeminiAdapter`, `GoogleADKAdapter`, `LettaAdapter`, `CodexAdapter`, `ParlantAdapter`.

### 3.6 WebSocket (only if not using the SDK)

```
wss://app.band.ai/api/v1/socket/websocket
```
Phoenix Channels protocol. Must join `chat_room`, `agent_rooms`, `agent_contacts`; must send heartbeats. The SDK does all this — direct implementation is significantly more work. **Default to the SDK.**

### 3.7 Env vars

```
BAND_API_KEY=...
BAND_AGENT_ID=...
```

> **Note:** each of the three agents is a distinct Band identity. You'll register and key them separately. Keep their IDs/keys clearly namespaced in env (e.g. `BAND_PARSER_*`, `BAND_REPRO_*`, `BAND_HYPOTHESIS_*`) so a worktree building one agent can't accidentally authenticate as another.

### 3.8 Operational caution

Three agents = three live WebSocket connections to keep alive simultaneously at the demo table. This is the scariest runtime risk. **Prove the three-way handshake (all three join, post, and receive via @mention) before building any agent's real logic.** Do not move on from the skeleton until the room transcript reads like a real conversation.

---

## 4. Arize Phoenix

**Role in TRIAGE:** makes the retry intelligence *visible*. Each repro attempt is a trace; judges watch the agent fail, adjust, and succeed across retries in a visual trace tree. The bounty bar is literally "evidence that Arize was used and **improved** the application" — so it must show improvement on-screen, not silently log.

**Verify current details before coding:**
- Packages: `arize-phoenix`, `openinference-instrumentation-anthropic`, `opentelemetry-sdk`.
- Confirm `phoenix.otel.register` signature and the collector endpoint against live docs.

### 4.1 Tracing setup (Python)

```bash
pip install arize-phoenix openinference-instrumentation-anthropic opentelemetry-sdk
```

```python
from phoenix.otel import register

tracer_provider = register(
    project_name="triage-bug-repro",
    auto_instrument=True   # auto-captures Anthropic/Claude calls as spans
)
```

With `auto_instrument=True`, all Claude/Anthropic calls become spans (prompts, completions, token counts) automatically.

### 4.2 Manual spans (the part that tells the story)

Wrap each retry attempt as a **parent** span, with a **child** span for browser execution. This is what produces the visual trace tree showing improvement across retries.

```python
from opentelemetry import trace
tracer = trace.get_tracer("triage")

with tracer.start_as_current_span("repro_attempt") as span:
    span.set_attribute("attempt.number", retry_count)
    span.set_attribute("github.issue_url", issue_url)
    span.set_attribute("bug.detected", False)
    # ... browser execution (child span) here
```

> Suggested hierarchy: `repro_attempt` (parent) → `browser_execution` + `hypothesis_generation` (children). Set `bug.detected` honestly per attempt so the fail→succeed flip is visible in the tree. **That flip is the demo's closer — don't fake it; build the retry so it's real.**

### 4.3 Two MCP servers (optional, for the build agent)

- **Phoenix Docs MCP** — real-time documentation search. Useful for *you* (Claude Code) to verify details while building.
  ```bash
  claude mcp add --transport http phoenix-docs https://arizeai-433a7140.mintlify.app/mcp
  ```
- **Phoenix Platform MCP** — live trace/project access (traces, spans, sessions, prompts, datasets, experiments).
  ```bash
  claude mcp add phoenix -- npx -y @arizeai/phoenix-mcp@latest \
    --baseUrl https://app.phoenix.arize.com --apiKey YOUR_PHOENIX_API_KEY
  ```

### 4.4 Env vars

```
PHOENIX_API_KEY=...
PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com   # or self-hosted URL
```

---

## 5. Full env var checklist

| Variable | Service | Source |
|---|---|---|
| `BROWSERBASE_API_KEY` | Browserbase | dashboard |
| `BROWSERBASE_PROJECT_ID` | Browserbase | dashboard → project settings |
| `BAND_API_KEY` (×3, per agent) | Band | dashboard → agent registration |
| `BAND_AGENT_ID` (×3, per agent) | Band | dashboard → agent UUID |
| `PHOENIX_API_KEY` | Arize Phoenix | app.phoenix.arize.com → settings |
| `PHOENIX_COLLECTOR_ENDPOINT` | Arize Phoenix | cloud default above, or self-hosted |

---

## 6. Language decision (resolve before writing shared code)

There's a real tension: **Stagehand is TS-native**, but the **Band SDK and Phoenix examples are Python**. Options:

- **Split-language:** Repro Agent in TS (best Stagehand support), Parser/Hypothesis + tracing in Python. Most "correct" per each SDK, but two runtimes to keep alive at 2am.
- **All-Python:** use the Stagehand Python SDK so everything is one runtime. Less Stagehand polish, simpler ops.
- **All-TS:** requires confirming TS support for Band + Phoenix is good enough.

**Do not start the shared Band module until this is decided** — it dictates the whole repo. Surface the tradeoff and get an explicit choice; don't default silently.

---

## 7. Hard rules — do not violate

1. **Verify against live docs before writing integration code.** This file is a baseline, not gospel. Where they conflict, live docs win — and tell me.
2. **All browser work in the Repro Agent.** Concentration is the Browserbase win condition.
3. **Every cross-agent message has an @mention.** No @mention = no recipient.
4. **Never name an agent generically.** `ReproAgent`, `HypothesisAgent`, `ParserAgent` only.
5. **New Browserbase session per retry** (no `sessionId`) — clean state + per-attempt replay URL.
6. **Messages for directed talk, events for logs.** Don't mix them.
7. **Prove the three-way Band handshake before building real agent logic.** Skeleton first.
8. **`bug.detected` must be honest.** The fail→succeed flip in the trace has to be real.
9. **If a needed detail isn't here and isn't in live docs you fetched, stop and ask.** Never improvise an endpoint, tool, or auth header.
