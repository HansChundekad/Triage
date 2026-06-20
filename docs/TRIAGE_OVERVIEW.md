# TRIAGE — Product Overview & Architecture

*An autonomous bug-reproduction agent. Built for UC Berkeley AI Hackathon 2026.*

---

## What we're building

**Triage** — an agent that reproduces software bugs by actually using your app.

A developer pastes in a GitHub issue — a bug report written in vague human language, like *"the app goes blank when I delete my last task."* Triage reads it, opens a real browser in the cloud, and clicks through the app trying to trigger the bug — typing, clicking buttons, exactly like a person would. When the app breaks, it screenshots the crash, captures the error, diagnoses the likely cause, and writes a clean report: exact steps to reproduce, what broke, and the root-cause hypothesis.

**One-liner:** *"It reproduces your bugs by actually using your app — not by reading your logs."*

---

## Why it matters

Every dev team has bugs someone reported but nobody else can reproduce. *"Works on my machine."* Those issues rot for weeks because reproducing them by hand is tedious. Triage automates that — and it does it by **using the app**, not by reading logs. That's the novel part, and it's what a judge remembers: a real browser breaking a real app on command.

---

## Companies we're targeting

Four integrations, each one load-bearing — not bolted on:

| Company | Role in Triage | Strategy |
|---|---|---|
| **Browserbase** (hero) | The real cloud browser that clicks through the app. Proof it's real automation, not scraping. | Concentrated in **one** agent for *depth*. |
| **Band** | The room where three agents talk and coordinate. The *conversation between* agents is the story. | Spread across **three** agents for *breadth* of coordination. |
| **Arize Phoenix** | Traces every attempt, so you can show the agent fail, adjust, and succeed. The "it got smarter" evidence. | Wraps the retry loop. |
| **Claude** | The reasoning brain across all agents (and the build tool via Claude Code). | Everywhere. |

All living under the **Ddoski's Toolbox** grand-prize track, because it's a tool built for developers.

### The elegant part: one loop, three bounties

When a repro attempt fails, an agent redirects another agent (**Band** coordination), which spins a fresh browser session and retries (**Browserbase**), and that whole failed-then-succeeded progression shows up in the trace (**Arize**). One mechanism, three wins.

---

## High-level architecture — what happens, in order

1. **You paste a GitHub issue URL** into a simple web page (the frontend).

2. **Issue Parser Agent** fetches the issue text via GitHub's API; Claude turns vague prose into clean structured steps — inferring the unstated *"add a task first"* precondition the user never mentioned. It posts the steps into the Band room, @mentioning the Repro Agent.

3. **Repro Agent** takes those steps, spins up a real Browserbase browser, and executes each as a natural-language Stagehand action — focus input, type task, click add, click delete. Screenshots every step, captures console errors.

4. **Repro Agent reports into the room**, @mentioning the Hypothesis Agent with the evidence (crash, error, screenshots).

5. **Hypothesis Agent** reads the evidence, reasons about root cause, and @mentions back its diagnosis. If the repro looks wrong or incomplete, it redirects: *"@ReproAgent retry with a slower delete"* — or the Repro Agent kicks back to the Parser: *"@ParserAgent step 3 found no Add button, re-read the issue."*

6. **On a failed attempt**, the retry logic logs it, spins a *fresh* Browserbase session, and tries again — and **Arize traces all of it** so the progression is visible.

7. **Claude synthesizes** everything into the final structured report — repro steps, root cause, embedded screenshots, session replay link — which renders on the frontend.

```
  [Frontend: paste GitHub issue URL]
              │
              ▼
   ┌──────────────────────┐
   │  Issue Parser Agent  │──┐  "@ReproAgent here are the steps"
   └──────────────────────┘  │
              ▲               ▼
   re-parse  │        ┌──────────────────────┐   real cloud browser
   (on fail) │        │     Repro Agent      │──► [ Browserbase ]
              │        └──────────────────────┘   focus→type→add→delete
              │               │
              │               ▼  "@HypothesisAgent here's the crash"
              │        ┌──────────────────────┐
              └────────│  Hypothesis Agent    │  diagnoses root cause,
       "retry w/ tweak"└──────────────────────┘  can redirect for retry
              │
              ▼
   [ retry loop ] ──► traced end-to-end by [ Arize Phoenix ]
              │
              ▼
   [Claude synthesis] ──► [Frontend: structured report + screenshots]

   All three agents live in one [ Band room ] and coordinate via @mentions.
```

---

## The three agents on Band

**Issue Parser Agent** — reads the GitHub issue, extracts structured repro steps (including unstated preconditions), and hands them off into the room. Its presence means a failed repro can route *back* to it for re-parsing — that's a real coordination loop, not a baton pass.

**Repro Agent** — the hands, and the Browserbase hero. Drives the cloud browser, executes each step, captures screenshots and errors, logs each browser action as a Band event, and reports findings via @mention. **All** browser depth lives here — concentrated, not spread, so the Browserbase usage is deep and visible.

**Hypothesis Agent** — the brain. Receives evidence when @mentioned, diagnoses root cause, and can send work *back* — redirecting the Repro Agent to retry with a tweak. That redirect is what turns a straight line into a genuine coordination loop.

### What the room transcript looks like to a judge

> **ParserAgent** → "@ReproAgent extracted 4 steps: focus input, type task, click add, click delete"
> **ReproAgent** → "@HypothesisAgent ran all 4 — app went blank, console threw TypeError on empty array"
> **HypothesisAgent** → "@ReproAgent confirmed, matches the report. Root cause: reading items[0] after delete. Repro valid."

That reads as agents **coordinating** — the bar for Band as a "key technology."

### Two non-negotiable rules (from the integration reference)

- **Agents only see messages they're @mentioned in.** Route deliberately — a message with no @mention reaches no one.
- **Never name agents generically.** Use "ReproAgent," "HypothesisAgent," "ParserAgent" — never "Agent" or "Bot." Generic names break @mention routing because the model treats them as roles, not names.

---

## Browserbase vs. Band — how we win both

These two don't compete; they live in different layers and reinforce each other.

- **Browserbase = depth in one agent.** Don't spread browser work across agents. Concentrate it in the Repro Agent so that one agent's browser usage is deep and visible. The win condition is the judge watching the live browser stream click through the app: focus → type → add → delete → crash. Multiple real Stagehand actions against a live URL, screenshots at each step, a session replay link in the report.

- **Band = breadth across agents.** The *coordination* is the story. The more the agents genuinely route work to each other — especially the retry redirects — the stronger it is. Band's strength comes from the conversation *between* agents; Browserbase's from the depth *within* one.

The retry loop that makes Band look like real coordination is the same loop where the Repro Agent spins a fresh Browserbase session and retries — which is also the Arize "it got smarter" trace.

---

## Where the hours go

Three agents, but not equal effort. The Parser and Hypothesis agents are mostly Claude reasoning + Band messaging — plumbing that subagents handle in parallel worktrees. **Your time goes into the Repro Agent's browser execution** — making Stagehand reliably click through and correctly detect whether the bug fired. That's the hard part and the hero, so it gets you.

**Caution:** three agents means three WebSocket connections, three things to keep alive at the table. Three is the sweet spot — enough for real coordination, few enough to not flake on stage. Resist adding a fourth unless everything else is done.

---

## Build order

The pipeline needs a stable, deterministic target to develop and rehearse against before any agent code is worth writing. So the build starts with:

1. **Buggy target app** *(FIRST)* — a deliberately buggy to-do app with a four-step click-through path (focus → type → add → delete) where the delete-to-empty transition crashes the render. Single static HTML file, deployed to Vercel, with a confused-user GitHub issue filed against it.
2. **Issue parsing** — GitHub fetch + Claude → structured steps.
3. **Browserbase + Stagehand executor** *(the hard part — your hours)*.
4. **Capture layer** — screenshots, console errors, bug-detection.
5. **Band coordination** — three agents, @mention routing, retry loop.
6. **Arize tracing** — wrap the retry loop in spans.
7. **Claude synthesis** — artifacts → structured report.
8. **Minimal frontend** — input, live log, report card.
