# TRIAGE

Autonomous bug-reproduction agent. A developer pastes a GitHub issue; TRIAGE
opens a real cloud browser, clicks through a live app to trigger the bug,
captures the crash, diagnoses the root cause, and writes a structured report.

Built for the UC Berkeley AI Hackathon 2026.

## Architecture (three agents, one Band room)

- **ParserAgent** (`triage/parser_agent/`) — GitHub issue → structured repro steps.
- **ReproAgent** (`triage/repro_agent/`) — drives a real Browserbase browser. **All** browser work lives here.
- **HypothesisAgent** (`triage/hypothesis_agent/`) — diagnoses root cause, can redirect ReproAgent to retry.

Integrations: Browserbase (cloud browser), Band (multi-agent coordination),
Arize Phoenix (retry-loop tracing), Claude (reasoning).

See `docs/TRIAGE_OVERVIEW.md` (source of truth) and `docs/TRIAGE_INTEGRATIONS.md`.

## Status

Phase 1 — repo scaffold. No agent logic or integration code yet.

## Setup

```bash
pip install -e ".[dev]"   # installs python-dotenv + pytest only in Phase 1
cp .env.example .env      # then fill in your keys
pytest                    # runs the config-loader tests
```
