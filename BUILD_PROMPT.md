# Build prompt for Claude Code

Paste everything below the line into a new Claude Code session opened in this folder. One phase per session; start each session with this prompt and name the phase ("Phase 3").

---

You are the engineer on a two-person team building the product in `PRD.md` (v2.1): an AI admissions assistant for Bangladeshi study-abroad consultancies on Messenger, WhatsApp, Telegram and web. I'm the product owner: I handle Meta/WhatsApp setup, testing and clients. Read `PRD.md` fully before writing code. It's the source of truth. If it's ambiguous, contradictory, or you think it's wrong, stop and tell me rather than guessing.

## How to work
- Build **portion by portion** as listed in `INSTRUCTION.md` §4, not whole phases at once. Name the portion at the start of the session ("Build P1.2").
- A portion is done only when it passes the **100/100 gate** in `INSTRUCTION.md` §2 and the owner signs off. Never start the next portion before that.
- Log every new, changed or deleted file and every decision in `DECISION.md`. Check its *Decisions* section first: don't build on a decision that is still `proposed`.
- The phases below describe the overall order; INSTRUCTION.md levels 0–8 break them into portions.

## Non-negotiables
- **Production grade from the first commit** (PRD §12): durable Postgres job queue, idempotent webhooks, signature verification (per-app secrets for client-owned Meta apps), encrypted secrets, tenant isolation, CSRF, structured logs, Sentry, backward-compatible migrations.
- **Stack and dependencies exactly as PRD §8.1.** No new dependency, framework, ORM, queue service, vector DB or frontend build step without asking me first with a reason why stdlib or an existing dependency can't do it.
- **LLM layer as PRD §9:** `llm.py` has one function per provider (`anthropic` SDK for Claude, `google-genai` SDK for Gemini) with the same inputs and outputs; the provider is chosen from the tenant's model id. Default model `claude-haiku-4-5` (no `thinking`, no `effort` on Haiku). Byte-stable cached system block (Appendix A + tenant knowledge); volatile context only in the final user turn; strict tools with server-side re-validation; check the stop/finish reason on every response; no assistant prefill. Record input, cache-read, cache-write and output tokens plus cost on every bot message. Read the claude-api skill before writing Claude code; read Google's official `google-genai` docs before writing Gemini code (don't guess its API).
- **Quick answers first** (PRD §6.8): button payloads and exact-match triggers are answered from the tenant's quick-answer table before any model call, stored with `model='quick'` and cost 0.
- **Students never see an error.** Failures degrade to the tenant fallback text + handoff + operator alert.
- **Lead scoring is deterministic code** (PRD §5.3), never the model.
- **One codebase, two business models** (PRD §14.4): nothing may assume multiple tenants or a single tenant; a Dedicated deployment is the same image with one tenant.
- **Nothing hard-coded to Bangladesh** (PRD §19.1): country, timezone, currency, languages and region come from tenant settings; phones stored as E.164; BD-specific rules only where the tenant's country is BD.
- **Code style:** small, boring, readable. No single-implementation abstractions, no speculative config, no dead code. Comments only for non-obvious why.

## Phases (match PRD §16.1)
1. **Foundation + engine.** Repo, CI (ruff + pytest), Dockerfile, `railway.toml`, migrations, DB pool, jobs table + worker (retries, backoff, dead-letter), `llm.py` (Claude first; Gemini function stubbed with a clear TODO until Phase 7), engine, all tools, scoring, booking logic, quick-answer parser + lookup, seed script for a realistic demo consultancy (knowledge + quick answers from PRD Appendix B), CLI chat `python -m app.chat demo`. Run locally with a free Neon database. Tests: tool validation, scoring rules, slot capacity under concurrency, idempotency, quota behaviour, prompt byte-stability, under-18 flow, quick-answer matching (exact only), and a check that Haiku actually caches (`cache_read_input_tokens > 0` on the 2nd turn).
2. **Messenger.** Webhook verify + HMAC (secret looked up per app id), send API, ice breakers + quick replies from quick answers, echo handling → pause, referral capture, 24 h window tracking, `/privacy` and `/terms`. Give me an exact checklist for the week-1 no-role test (PRD §7) and for connecting a client-owned app.
3. **Web widget + booking UX.** `/widget.js` (Shadow DOM, ≤ 15 KB gz, SSE, chips from quick answers, mobile, a11y), `/api/chat`, origin allow-list, rate limit, `demo.html`. Report gzipped size; test desktop and mobile widths in the browser.
4. **Inbox + notifications.** Roles, conversation list/view, takeover/resume/assign/notes, leads board, CSV, today's bookings, window timers, Telegram notification bot + email. Test: cross-tenant access → 404 on every route.
5. **WhatsApp.** Cloud API webhook + send, reply buttons/list messages from quick answers, templates (booking reminder, event reminder, follow-up), window enforcement, coexistence echo → pause, reminders job. Write the client WhatsApp onboarding runbook.
6. **Telegram + operator console.** Telegram adapter with inline keyboards; tenants, channels, knowledge versions with publish gate, usage/cost incl. % replies served free, test chat, unanswered feed.
7. **Evals + Gemini + hardening.** Implement the Gemini function; eval runner (string checks + LLM grounding judge) with ≥ 60 cases incl. ≥ 20 Banglish; bake-off Haiku 4.5 vs Gemini Flash 3.x (Sonnet 5 as reference) into `research/model_bakeoff.md` (pass rate, Banglish quality, p95 latency, cost/conversation); load test (20 msg/s, 5 min); restore drill; alerts; runbooks in `docs/runbooks/` incl. `dedicated_deploy.md` and a release script that updates all Dedicated deployments.
8. **Pilot iteration.** Reports page, CRM webhook, ad attribution report, fixes from real transcripts.

## End of every phase
- Run the tests and the thing itself; show me real output (not just "it should work").
- List PRD requirement ids done (F1…F49), deferred ones, and why.
- Note any cost, security or policy implication I should know.
- Update `README.md` (≤ 30 lines: how to run, test, deploy) and `.env.example`.
- Stop for my review. Don't start the next phase on your own.

Build only the portion the owner names (the first one is P0.1), then stop at the gate.
