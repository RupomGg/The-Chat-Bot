# DECISION.md: Decisions and change log

Every decision and every file created, changed or deleted is recorded here, newest at the bottom of each section. If it's not in this file, it didn't officially happen.

- **Decisions** (`D-###`): a choice between options, with the reason. Status: `proposed` → `accepted` / `rejected` (by the owner).
- **Change log** (`C-###`): one entry per portion or fix, listing every file touched.
- **Open items**: things noticed that belong to a later portion.

---

## Entry templates

```markdown
### D-### Title
- Date:
- Status: proposed | accepted | rejected
- Context: what needed deciding
- Options: A) … B) …
- Decision: …
- Why: …
- Affects: files / portions / PRD sections
```

```markdown
### C-### Portion P?.? (or fix: short title)
- Date:
- Type: portion | fix | docs | refactor
- New files:
  - `path`: its job
- Changed files:
  - `path`: what changed · why · who depends on it
- Deleted files:
  - `path`: why · replaced by
- Decisions referenced: D-###
- Gate result: G1 … G9 (paste the summary lines: tests passed, coverage %, ruff)
- `# pragma: no cover` uses: none | list with reason
- Owner sign-off: pending | yes (date)
```

---

## Decisions

### D-001 Product scope and stack baseline
- Date: 2026-09-23
- Status: accepted
- Context: baseline decisions made while writing the PRD.
- Decision: study-abroad consultancies in Bangladesh (international later, PRD §19); channels Messenger, WhatsApp, Telegram, web; Python + FastAPI + Postgres (Neon) + Postgres job queue + Jinja2; default model `claude-haiku-4-5` with Gemini Flash as tested challenger; quick answers without AI; Hosted and Dedicated business models from one codebase; client-owned Meta apps/WABAs (no Meta verification for us in v1).
- Why: see PRD v2.1 §§1, 8, 9, 14, 19, 20.
- Affects: all portions.

### D-002 Python version
- Date: 2026-09-23
- Status: **accepted** (owner, 2026-09-23): Python 3.13.1
- Context: PRD §8.1 says Python 3.12; the local machine has Python 3.13.1 and no 3.12.
- Options: A) Use 3.13 everywhere (local, CI, Docker) and update PRD §8.1. B) Install 3.12 locally to match the PRD.
- Recommendation: **A**. All planned dependencies support 3.13, and one version everywhere avoids "works on my machine" bugs.
- Decision: **A**, Python 3.13 locally, in CI and in the Docker image (`python:3.13-slim`). `pyproject.toml` will require `>=3.13,<3.14`.
- Affects: `pyproject.toml`, CI (P0.2), Dockerfile (P7.2), PRD §8.1.

### D-003 PostgreSQL for local tests
- Date: 2026-09-23
- Status: **accepted** (owner, 2026-09-23): local PostgreSQL
- Context: tests from P1.1 on need a real Postgres (constraints, locks and SKIP LOCKED can't be faked). No Postgres or Docker is installed locally.
- Options: A) Install PostgreSQL 16 for Windows locally (free, fastest tests, works offline). B) Use a Neon free-tier **test branch** over the internet (nothing to install, slower, needs internet, shared by test runs). C) Install Docker Desktop and run Postgres in a container.
- Recommendation: **A** for daily work; CI uses a Postgres service container (P0.2). Tests create and drop their own temporary database, so they never touch real data.
- Decision: **A**, PostgreSQL 16 installed locally on Windows (same major version as PRD §8.1 and CI). Tests read `TEST_DATABASE_URL`, create a throwaway database per test session and drop it afterwards.
- Owner action before P1.1: install PostgreSQL (steps in INSTRUCTION.md §5.1).
- **Amended by D-008:** the major version is 18, not 16.
- Affects: `tests/conftest.py`, `.env.example`, P1.1 onward.

### D-004 Test tooling dependencies
- Date: 2026-09-23
- Status: **accepted** (owner asked for the best option, 2026-09-23): A + B, with B limited
- Context: the gate (INSTRUCTION.md §2) needs branch coverage. PRD §8.1 lists `pytest` and `ruff` only.
- Options: A) Add `coverage` as a dev-only dependency (not shipped in the Docker image). For async tests, use the `anyio` pytest plugin that already comes with FastAPI's dependencies, so no `pytest-asyncio`. B) Also add `hypothesis` for property-based tests of parsers (phones, redaction, knowledge).
- Recommendation (original): A only.
- Decision: **A + B.** `coverage` for the gate; `hypothesis` **only** for pure text-handling code: phones (P2.1), knowledge/quick-answer normalization (P2.2), redaction (P2.5). Settings: `derandomize=True` (same inputs every run, so gate G7 stays stable), `deadline=None` on slow machines, max 500 examples per test. Every bug hypothesis finds becomes a normal named regression test too.
- Why: the owner's priority is "no underlying bug"; messy student text (Bangla/English digits, emoji, spacing) is where hand-written cases miss things. Both are dev-only and never shipped in the Docker image.
- Affects: `pyproject.toml` `[dev]` extras, PRD §8.1 dependency list, INSTRUCTION.md P2.1/P2.2/P2.5.

### D-005 Settings are added portion by portion
- Date: 2026-09-23
- Status: **accepted** (owner proceeded to P0.2 without objection, 2026-09-23)
- Context: PRD Appendix E lists every environment variable for the finished product. Requiring all of them in P0.1 would force fake Meta/Telegram/Resend/Sentry values before any code uses them.
- Options: A) Require all Appendix E variables now. B) Each portion adds the variables its own code uses, with validation and tests.
- Decision (built this way in P0.1): **B.** P0.1 requires `ENV`, `DATABASE_URL`, `FERNET_KEY`, `SESSION_SECRET`, `PUBLIC_BASE_URL`. `SENTRY_DSN` moves to the observability portion; channel tokens move to P5.x.
- Why: no unused settings, so no fake values; every variable is validated by the code that needs it.
- Affects: `app/config.py`, `.env.example`, each later portion.

### D-006 API docs pages off in production
- Date: 2026-09-23
- Status: **accepted** (owner proceeded to P0.2 without objection, 2026-09-23)
- Context: FastAPI serves `/docs` and `/openapi.json` by default, which list every route to anyone.
- Decision (built this way in P0.1): on in `test`/`staging`, off in `production` (PRD §12.2 hardening).
- Affects: `app/main.py`.

### D-007 PyYAML as a dev dependency
- Date: 2026-09-23
- Status: **accepted** (owner, 2026-09-23)
- Context: GitHub Actions can't run locally, so the P0.2 corner cases (right Python version, Postgres service, gate commands, no hidden failures, no secrets) are checked by a test that reads `ci.yml`. That needs a YAML parser. PyYAML was already installed as a transitive dependency of `uvicorn[standard]`, but relying on a transitive dependency is fragile.
- Decision (built this way in P0.2): pin `pyyaml==6.0.3` in the `[dev]` extras. Dev-only, never shipped.
- Affects: `pyproject.toml`, `tests/test_ci.py`.

### D-008 PostgreSQL 18 instead of 16
- Date: 2026-09-23
- Status: **accepted** (owner, 2026-09-23)
- Context: the owner installed PostgreSQL 18.6 (EDB installer). The plan said 16. Local, CI and production must share the major version.
- Options: A) Move everything to 18. B) Also install 16 locally on another port.
- Decision: **A.** Local 18.6, CI `postgres:18`, production Neon 18. Before creating the production database, confirm Neon offers 18; if not, use 17 in both production and CI (one-line change + test).
- Why: nothing we use differs between 16 and 18 (constraints, advisory locks, `FOR UPDATE SKIP LOCKED`, `timestamptz`, `numeric`); one version everywhere; longest support window.
- Affects: `.github/workflows/ci.yml`, `tests/test_ci.py`, PRD §8.1, INSTRUCTION.md §5, D-003.

### D-009 Synchronous database driver, proven on Linux, Windows and macOS
- Date: 2026-09-23
- Status: **accepted** (owner, 2026-09-23): "fix D-009 for Linux, Windows, Mac, Android"
- Context: psycopg's async mode doesn't work with Windows' default event loop (Proactor). Async code would pass on the Linux server and CI but break on the owner's Windows machine, or need special loop settings everywhere.
- Options: A) Async psycopg + force the selector event loop on Windows. B) Plain (sync) psycopg + `psycopg_pool.ConnectionPool`; FastAPI runs `def` endpoints in its thread pool.
- Decision (built this way in P1.1): **B.**
- Why: the same code behaves the same on Windows and Linux; simpler code and tests; our load (a few messages per second per tenant) is far below the thread pool's limits. Revisit only if measured load needs it.
- Affects: `app/db.py`, `app/main.py`, every later portion that touches the database (endpoints are `def`, not `async def`).
- **Cross-platform (owner request):** the server code must work the same on Linux (production), Windows and macOS (development). Proven by CI running the full gate on `ubuntu-latest`, `windows-latest` and `macos-latest`, each with PostgreSQL 18 and the same limited `chatbot_test` login (C-009). `psycopg[binary]` ships ready-made builds for all three, including Apple Silicon Macs.
- **Android / iPhone:** these are where students chat (Messenger, WhatsApp, Telegram, the website widget in the phone browser), not where the server runs, so D-009 doesn't affect them. What must work on phones is the widget: real Android Chrome and iPhone Safari checks are required in P5.2.

### D-010 Tenant isolation enforced by the database
- Date: 2026-09-23
- Status: **accepted** (owner signed off P1.2, which is built on it, 2026-09-23)
- Context: PRD §10 gives tables a `tenant_id`, but plain foreign keys would still let the database store, for example, client A's contact on client B's channel if app code had a bug. Tenant mix-ups are the worst kind of bug for a multi-client product (one consultancy seeing another's students).
- Options: A) Plain foreign keys; rely on app code (P6.1 cross-tenant tests) only. B) Composite foreign keys `(tenant_id, parent_id)` → `UNIQUE (tenant_id, id)` on parents, plus `tenant_id` on `messages`, `notes`, `event_registrations`.
- Decision (built this way in P1.2): **B**, as a second line of defence under the app-level checks.
- Also in the schema: no foreign key cascades or nulls anything (deleting a client with data is refused); minors (`adult = false`) can't have a phone stored; knowledge can't be published unless its evals passed; one web channel per client; no double booking of the same slot by the same student; a global audit event can't reference a conversation (a composite FK is skipped when a column is NULL).
- Why: invalid data becomes impossible, not just unlikely. Cost: one extra column on three tables and slightly longer FK definitions.
- Affects: `migrations/001_init.sql`, PRD §10 (as-built note added), every later portion that inserts rows (must pass `tenant_id`).

### D-011 Security parameters
- Date: 2026-09-23
- Status: **accepted** (owner, 2026-09-23): "password minimum 8 digit with regular rules, do OWASP, 8 hours", "no Bangla text or emoji allowed"; confirmed "regular login: 8+ with uppercase, lowercase, special character and number; rest keep secure"
- Context: P1.3 needed concrete values for password hashing, password rules and CSRF tokens. First version used 12-256 characters, any characters (NFKC-normalized) and 12-hour CSRF tokens; the owner changed them.
- Options discussed for password rules: A) OWASP style: 8+ characters, any characters, no forced composition, block the ~10,000 most common passwords (needs a list download). B) Classic composition rules. C) Both. The owner asked for "regular rules", OWASP hashing, and no Bangla/emoji, and didn't approve the list download.
- Decision (built):
  - Staff passwords: **8-256 characters; standard keyboard characters only** (printable ASCII: English letters, digits, symbols, spaces; Bangla, emoji, accented letters, tabs, newlines, NUL and non-breaking spaces are rejected); **must contain an uppercase letter, a lowercase letter, a digit (ASCII only; Bangla, Arabic-Indic and full-width digits don't count) and a symbol** (a space is not a symbol). The error lists every broken rule at once.
  - Hashing at **OWASP** strength: stdlib `hashlib.scrypt`, **N=2^14, r=8, p=5** (OWASP's equivalent low-memory row: 16 MiB per login instead of 128 MiB at N=2^17, p=1; measured 0.5 s vs 0.8 s per login; changed in C-013 after the owner asked whether security was excessive and said "rest keep secure"), 16-byte salt, stored as `scrypt$N$r$p$salt$hash` (parameters can be raised later without breaking logins). Unicode normalization removed (passwords are ASCII only now).
  - Login attempts over 1,024 characters are rejected without hashing.
  - CSRF tokens: **8 hours**, bound to the session id, up to 60 s clock skew, signed with a key derived for CSRF only.
  - Webhook checks: Meta `X-Hub-Signature-256` (exactly `sha256=` + 64 hex) and Telegram's secret header (exact match), both constant-time; malformed input returns False, never raises.
- Not included (can be added later with owner approval): a common/breached-password block list. OWASP recommends it; composition rules alone let predictable passwords like `Password1!` through.
- Affects: `app/security.py`, `tests/test_security.py`; later P6.1 (login, CSRF).

### D-012 Universal core + industry packs
- Date: 2026-09-23
- Status: **accepted** (owner, 2026-09-23): "I want to make my bot universal for any project ... a financial institution ... a pet care centre"
- Context: everything so far was framed for study-abroad consultancies. The owner wants any kind of business later.
- Options: A) Stay consultancy-only and rewrite later. B) Universal core + one "industry pack" per industry (settings and text, no code), study_abroad first. C) Build many packs now.
- Decision: **B.** The core (channels, AI engine, inbox, bookings, jobs, security, billing, performance log) never hard-codes an industry; each tenant has `industry`, and the engine loads that pack (profile fields, scoring rules, stage labels, prompt, knowledge template, quick answers, eval questions, compliance notes). Only the study_abroad pack is built until a real client in another industry signs. Sales keep targeting one industry at a time.
- Database: generic pipeline stages `new, contacted, qualified, booked, in_progress, won, lost` (`in_progress` added so stages like "counselled/applied" keep a slot); `tenants.industry` defaulting to `study_abroad`.
- Why: pivoting is cheap now (only `contacts.status` in built code was industry-specific) and expensive later.
- Caution: regulated industries (finance, health) need their own compliance rules and legal review before launch.
- Affects: `migrations/002_universal_core.sql`, PRD §0/§5.3/§10, INSTRUCTION.md Level 2 (new P2.0 pack loader) and P2.3/P4.3/P7.1.

### D-013 Performance log (`bot_turns`)
- Date: 2026-09-23
- Status: **accepted** (owner, 2026-09-23): "log ... other logs the bot can collect for performance optimization later"
- Decision: new table `bot_turns`, one row per bot reply, **metadata only**: message id (plain reference), when the student's message arrived, source (`quick`/`llm`/`fallback`/`handoff`), channel, model, language, total latency, AI time, tokens (input, cache read/write, output), exact cost, tools used, stop reason, error code. No message text and no phone number, so it can be kept after message text is deleted by retention. AI usage moved here from `messages` (which now hold content only). Funnel events (button clicks, bookings, handoffs) keep going to `audit_events`.
- Rules in the database: an AI reply must name its model; a button answer can't cost money; no negative times, tokens or cost; error code ≤ 100 characters; tied to its tenant by composite key.
- Affects: `migrations/002_universal_core.sql`, PRD §10; later P4.2/P4.4 (write a row per reply), P6.3 (usage view), P7.2 (retention: keep `bot_turns` longer than messages).

### D-014 Minors' phone numbers are stored (owner-accepted legal risk)
- Date: 2026-09-23
- Status: **accepted** (owner, 2026-09-23): chose "Always store it" over storing with a consent flag, a scrambled copy, or not storing
- Context: 001 made the database refuse a phone number when `adult = false` (Bangladesh PDP Act 2026 requires verifiable parental consent for under-18s; fines up to ৳25 lakh, risk mainly on the consultancy).
- Decision: every student's phone number is stored, including under-18s. `adult` is still recorded; the bot suggests a guardian join counselling.
- Risk and mitigation: **owner-accepted legal risk.** Before the first consultancy signs, a lawyer should confirm how its privacy notice/DPA covers parental consent. Revisit this decision if a client or regulator objects; a consent flag can be added later without losing data.
- Affects: `migrations/002_universal_core.sql` (drops `contacts_check`), PRD §5.2/§12.3/§17/Appendix A/Appendix C, INSTRUCTION.md P4.3.

### D-015 Quick answers editable per company + contact-detail checks for international use
- Date: 2026-09-23
- Status: **accepted** (owner, 2026-09-23): "I want these modular based on company so that I can fix those questions' expected answers from my admin backend or user can"; "what else should it control, like email, if I'm talking about international"; approved the plan with "g"
- Decision:
  - Quick answers move from the knowledge file into the database, **per company**: code, trigger phrases, answers per language, follow-up buttons, optional action, on/off.
  - **Who can edit:** the operator (any company) and the company's admin (own company only); counsellors can't. Enforced in the admin screens (Level 6); the database already keeps companies apart.
  - **Company-admin edits go live immediately** (owner didn't choose between "immediately + undo" and "wait for approval"; the recommended default was applied). Every change is recorded by the database itself in `quick_answer_history` (before, after, who, when) and can be undone. An approval step can be added later if needed.
  - One trigger phrase belongs to at most one quick answer per company (database rule, safe under concurrent edits).
  - New contact-detail checks (P2.1b): email, name, country, year-month, timezone, https URL. `contacts.email` added. `tenants.settings` added for pack settings (e.g. `served_countries`).
- Affects: `migrations/003_quick_answers_and_contact_details.sql`, PRD §6.8/§10, INSTRUCTION.md P1.4, P2.1b, P2.2, and Level 6 admin screens.

### D-016 Pin `tzdata` as a runtime dependency
- Date: 2026-09-24
- Status: **accepted** (built in P2.1b under the approved plan; tiny, official source of timezone data)
- Context: `valid_timezone` uses Python's `zoneinfo`. Windows has no system timezone database and slim Linux Docker images may not either. `tzdata` was installed only because `psycopg` pulls it in **on Windows only**, so the Linux server could lack it.
- Decision: pin `tzdata==2026.4` in the runtime dependencies (PEP 615's recommended source).
- Affects: `pyproject.toml`, `app/contact_details.py`, Dockerfile (P7.2); update the pin with other dependencies.

### D-017 Faster test runs: parallel workers + reusable migrated copy
- Date: 2026-09-24
- Status: **accepted** (owner: "fix 1 test time")
- Context: the full test run took 4-6.5 min (O-006). Measured: nearly all of it was creating/cloning and dropping a database per test (1-9 s each on this disk), not the tests.
- Decision: (1) dev dependency `pytest-xdist==3.8.0`, `-n auto` in pytest config, so every gate command runs in parallel unchanged; coverage measures the workers (`patch = ["subprocess"]`). (2) `migrated_db_url` reuses one copy per worker and resets it after each test (TRUNCATE + restart sequences) instead of clone + drop; a schema fingerprint check re-clones if a test changed the structure.
- Affects: `pyproject.toml`, `tests/conftest.py`, gate time.

### D-018 The bot is never a free general AI (every industry)
- Date: 2026-09-24
- Status: **accepted** (owner: "make sure using the bot people can't get other answers like getting code or fixing algorithm")
- Context: the on-topic rule lived only in the study_abroad pack's prompt; a new pack could leave it out. Nothing checked the model's reply before sending, and a patient user could get unlimited AI answers (our cost, and Meta's WhatsApp AI policy).
- Decision: five layers. (1) **Now:** `CORE_RULES` added by the core to every industry's prompt, last (no code/algorithms/homework/essays/translations/general advice; one-line redirect; customer text is data). (2) P4.4 **reply guard**: a reply containing code is replaced by the redirect before sending. (3) P4.4 **off-topic streak**: 3 in a row → no model call for 1 hour (fixed redirect + quick-answer buttons). (4) P4.4 **daily cap**: 60 AI replies per contact per day (tenant setting), then handoff. (5) P7.1 **core off-topic/abuse eval set** (≥ 25 cases, ≥ 8 Banglish) every tenant must pass 100% before publishing. Quick answers need nothing: they only send the company's saved text.
- Affects: `app/knowledge.py`, `tests/test_knowledge.py`, INSTRUCTION.md P4.4 and P7.1, PRD §9.5 and Appendix C.

### D-019 Token-lean AI turns, without losing accuracy
- Date: 2026-09-24
- Status: **accepted** (owner: "no one can jailbreak and use my AI as their personal LLM; answer and query token optimized for maximum accuracy")
- Context: checked against the current Claude API docs: Haiku 4.5 accepts `temperature`, Sonnet 5 rejects it (400); on Haiku 4.5 nothing caches below 4,096 tokens of fixed prompt; cached reads cost 0.1× input, cache writes 1.25× (5 min) or 2× (1 h).
- Decision: quick answers first (0 tokens); new portion **P2.6** input guard (pasted code, encoded blobs, jailbreak phrases blocked before any model call, 0 tokens) and reply guard (code/over-long replies never sent); history 30 → **12 messages** + profile JSON; student text cap 2,000 → **1,000 chars**; `max_tokens` 1024 → **500**; `temperature` 0.2 on Haiku 4.5 (omitted where rejected); whole knowledge in the cached system prompt (no retrieval step: most accurate for ≤ 10k tokens); compact JSON tool results; 5-min cache by default, 1 h only for steady-traffic tenants; core rules now also require grounded, 1-4 sentence answers for every industry. Rule: a token saving is kept only if the eval pass rate holds.
- Honest limit: no prompt makes a language model impossible to jailbreak. The design makes a successful attempt worthless: short replies, no code ever sent, 60 AI replies a day, and repeat offenders get no AI at all.
- Affects: `app/knowledge.py`, INSTRUCTION.md P2.6/P4.1/P4.2/P4.4, PRD F8, §9.1, §9.2.

### D-020 Industry-neutral names in the core
- Date: 2026-09-24
- Status: **accepted** (owner: "how will I change these when I find a different industry client" → "g")
- Context: the code is industry-free, but the plan still named core things after study abroad: P2.4 "counselling slots", the AI tool `book_counselling`, and handoff reasons like `visa_case` fixed in the core.
- Decision: core names are neutral: "appointment" (P2.4), tool `book_appointment`; `request_handoff` reasons = core (`asked_for_human`, `complaint`, `unanswered`, `integrity`) + each pack's `handoff_reasons`; packs get `[terms]` (appointment, staff) so screens and messages say "counselling session"/"counsellor" for study abroad and "vet visit"/"vet" for pet care. The database role value `counsellor` stays (internal, never shown; the screen shows the pack's staff label): renaming it would need a migration for no customer-visible gain.
- New industry = a new pack folder, no code or database change (PRD §0).
- Affects: INSTRUCTION.md P2.4/P4.3, PRD §5 flow, F14, §9.4, Appendix A; `packs/study_abroad/prompt.md`.

---

## Change log

### C-001 Build process documents
- Date: 2026-09-23
- Type: docs
- New files:
  - `INSTRUCTION.md`: portion-by-portion build plan, the 100/100 gate, bug-handling rules, prerequisites.
  - `DECISION.md`: this file; decisions, change log, open items.
- Changed files:
  - `BUILD_PROMPT.md`: added a "How to work" section pointing to INSTRUCTION.md and DECISION.md; phases now map to INSTRUCTION.md levels · why: the build now goes portion by portion with a hard gate · nothing depends on it except new sessions.
- Deleted files: none
- Decisions referenced: D-001 (accepted); D-002, D-003, D-004 (proposed)
- Gate result: n/a (no code)
- Owner sign-off: yes (2026-09-23), owner continued the build on top of it

### C-002 Owner decisions D-002, D-003, D-004
- Date: 2026-09-23
- Type: docs
- New files: none
- Changed files:
  - `DECISION.md`: D-002, D-003, D-004 set to accepted with details.
  - `PRD.md` §8.1: Python 3.12 → 3.13; dev dependencies `coverage`, `hypothesis` listed · why: D-002, D-004 · depends: INSTRUCTION.md, BUILD_PROMPT.md read it.
  - `INSTRUCTION.md`: §5 prerequisites updated; new §5.1 PostgreSQL install steps; property-based tests added to P2.1, P2.2, P2.5 · why: D-003, D-004.
- Deleted files: none
- Decisions referenced: D-002, D-003, D-004
- Gate result: n/a (no code)
- Owner sign-off: yes (2026-09-23), owner continued the build on top of it

### C-003 Portion P0.1: Project skeleton and tooling
- Date: 2026-09-23
- Type: portion
- New files:
  - `pyproject.toml`: project metadata; all runtime dependencies pinned to exact versions (PRD §8.1); dev extras `pytest`, `coverage`, `ruff`, `hypothesis`, `httpx`; pytest config (warnings are errors, strict markers, `live` marker), coverage config (branch coverage on `app/`), ruff config (incl. security rules `S`).
  - `app/__init__.py`: package marker.
  - `app/config.py`: loads and validates settings once at startup; frozen `Config`; every problem reported at once; errors name the variable, never the value; `repr` masks secrets.
  - `app/main.py`: `create_app()` factory; config loaded at startup (fail fast); `GET /healthz`; API docs off in production (D-006).
  - `tests/__init__.py`: package marker (lets test modules import each other's helpers if needed later).
  - `tests/conftest.py`: shared fixtures `env_vars`, `config`, `client`.
  - `tests/test_config.py`: 50 tests: each required variable missing, blank/whitespace values, all problems reported together, no secret values in errors, whitespace stripping, ENV values, invalid Fernet keys (3 kinds), session secret length boundary (31/32), 8 malformed database URLs, 3 valid ones incl. IPv6, http vs https per environment, uppercase `HTTPS`, missing ENV + http URL, relative/ftp/host-less base URLs, trailing slash, immutability, secret masking in `repr`/`str`, reading `os.environ` by default.
  - `tests/test_health.py`: 8 tests: `/healthz` 200 + body, no secrets in body, POST → 405, unknown route → 404, bad config fails at startup, config from environment, docs on outside production and off in production.
  - `.gitignore`: ignores `.venv`, `.env*` (except `.env.example`), caches, coverage files.
  - `.env.example`: the five P0.1 variables with generation commands.
  - `README.md`: setup, run, test commands.
  - `.env` (local only, git-ignored, **not a deliverable**): generated keys for the manual check.
  - `.venv/` (local only, git-ignored): virtual environment.
- Changed files:
  - `INSTRUCTION.md` §2 G5: the gate command changed from `pytest -W error` to "config-enforced" · why: `-W error` on the command line overrides the one narrow upstream ignore, so G5 failed on a Starlette warning that isn't our code; `pyproject.toml` already makes every warning an error on every run · depends: every future gate run.
- Deleted files: none
- Decisions referenced: D-002, D-004, D-005 (proposed), D-006 (proposed)
- Gate result:
  - G1: `58 passed` (0 failed, 0 skipped, 0 xfail)
  - G2/G3: `app\config.py 61 stmts, 18 branches, 100%`; `app\main.py 100%`; TOTAL 100% lines + branches
  - G4: `ruff check`: All checks passed; `ruff format --check`: 12 files already formatted
  - G5: `filterwarnings` starts with `"error"`; one narrow ignore (Starlette/anyio deprecation, upstream), see open items
  - G6: reverse file order: 58 passed
  - G7: three runs: 58 passed ×3
  - Extra (mutation check): 5 deliberate bugs injected into `config.py` (production allows http; length off by one; secrets unmasked; blanks not stripped; mysql accepted): **5/5 caught**; file restored, 58 passed
  - G8: real server via uvicorn: `GET /healthz` → `{"status":"ok"}` HTTP 200; `GET /nope` → 404; starting with `FERNET_KEY` removed → `ConfigError: FERNET_KEY: missing`
  - G9: this entry
- `# pragma: no cover` uses: none
- Bugs found during the portion: none in our code. Gate G5 was defined wrongly (fixed above).
- Owner sign-off: yes (2026-09-23), given by asking to proceed to P0.2

### C-004 Expand .gitignore before the owner's first push
- Date: 2026-09-23
- Type: docs
- New files: none
- Changed files:
  - `.gitignore`: grouped with comments; added `*.pem`, `*.key`, `venv/`, `*.log`, `*.dump`, `*.sql.gz`, `.vscode/`, `.idea/`, `*.swp`, `Thumbs.db`, `desktop.ini`, `.DS_Store` · why: keep secrets, logs, database dumps and editor/OS files out of GitHub · depends: owner's git workflow (O-002).
- Deleted files: none
- Verification: in a scratch repo (not the project), 15 paths that must be ignored (`.env`, `.env.local`, `.env.production`, `.venv/`, caches, `*.log`, `*.pem`, `.vscode/`, `Thumbs.db`, `*.dump`, …) → all ignored; 8 that must be tracked (`.env.example`, `app/config.py`, tests, `pyproject.toml`, `migrations/001_init.sql`, docs, `.gitignore`) → all tracked.
- Tests: unchanged (no code touched).
- Owner sign-off: yes (2026-09-23), owner continued the build on top of it

### C-005 Portion P0.2: Continuous integration
- Date: 2026-09-23
- Type: portion
- New files:
  - `.github/workflows/ci.yml`: on every push (all branches) and pull request: Python 3.13, Postgres 16 service with health check, `TEST_DATABASE_URL` ready for P1.1, then ruff check, ruff format check, pytest, coverage 100% (lines + branches), reverse-order run. Read-only permissions, 15-minute timeout, superseded runs cancelled, no secrets.
  - `tests/test_ci.py`: 10 tests on the workflow file: triggers, Python version = `pyproject.toml`, Postgres 16 + health check, every gate command present, coverage fail-under 100, no `continue-on-error` / `|| true`, no `secrets.`, least privilege + timeout, warnings-as-errors config with no command-line `-W`, branch coverage on.
- Changed files:
  - `pyproject.toml`: `pyyaml==6.0.3` added to `[dev]` (D-007) · depends: `tests/test_ci.py`.
- Deleted files: none
- Decisions referenced: D-002, D-003, D-007 (proposed)
- Action versions: `actions/checkout@v7`, `actions/setup-python@v7` (latest releases checked on GitHub, 2026-09-23).
- Gate result:
  - G1: `68 passed`
  - G2/G3: TOTAL 100% lines + branches (`app/` unchanged: 72 stmts, 18 branches)
  - G4: ruff check: All checks passed; format: 13 files already formatted
  - G5: config-enforced; no command-line `-W` in CI (tested)
  - G6: reverse order: 68 passed
  - G7: 68 passed ×3
  - Local replay of every `run:` step from `ci.yml` (Git Bash, venv Python): 5/5 PASS
  - Failure proof: temporary failing test → pytest exit 1; temporary uncovered code → coverage report exit 2; temporary unused import → ruff exit 1. All temporary files removed; suite back to 68 passed.
  - G8 (manual, owner): after the first push, open the repo's **Actions** tab and see a green run. Then push a branch with a deliberately failing test → red; delete the branch.
  - G9: this entry
- Harness note: the first local replay failed because Python's `subprocess` resolved `bash` to the Windows WSL launcher (no Linux installed), not Git Bash. That was a test-harness problem, not a workflow bug; replayed directly in Git Bash instead.
- `# pragma: no cover` uses: none
- Owner sign-off: yes (2026-09-23): owner's GitHub Actions screenshot shows CI #1 (6e4595c) and CI #2 (f597125) green; each run = 3 jobs (ubuntu, windows, macos) with fail-fast off, so all three passed

### C-006 Switch PostgreSQL 16 → 18 (D-008)
- Date: 2026-09-23
- Type: refactor
- New files: none
- Changed files:
  - `tests/test_ci.py`: expects `postgres:18`; test renamed `test_postgres_18_service_with_health_check` · changed **first**, confirmed failing (1 failed, 9 passed) before the workflow change.
  - `.github/workflows/ci.yml`: service image `postgres:16` → `postgres:18` · depends: `tests/test_ci.py`.
  - `PRD.md` §8.1: DB row says PostgreSQL 18 + Neon availability check.
  - `INSTRUCTION.md` §5 table + §5.1: PostgreSQL 18 installed; PATH `...\PostgreSQL\18\bin`; steps 4–5 still to do.
  - `DECISION.md`: D-003 amended; D-008 added.
- Deleted files: none
- History note: C-005 still says "Postgres 16"; that is what was true when it was written and is left unchanged.
- Gate result: G1 68 passed · G2/G3 100% lines + branches · G4 clean (13 files formatted) · G6 68 passed · G7 68 passed ×3 · no remaining `16` references outside history.
- Local check: `psql (PostgreSQL) 18.6` at `C:\Program Files\PostgreSQL\18\bin`.
- Owner sign-off: yes (2026-09-23), owner continued the build on top of it

### C-007 Local PostgreSQL set up (owner + Claude)
- Date: 2026-09-23
- Type: docs (environment)
- What happened: the owner had forgotten the `postgres` admin password. Reset by temporarily setting the two `host all all` lines in `pg_hba.conf` to `trust`, restarting the service, setting passwords, and creating role `chatbot_test` (LOGIN, CREATEDB). The owner then set both lines back to `scram-sha-256` and restarted.
- Verified: `pg_hba.conf` lines 115/117 = `scram-sha-256`; right password → connected as `chatbot_test` on PostgreSQL 18.6; wrong password → `password authentication failed`; no password → refused; role can CREATE and DROP a database.
- Files: `.env` (local, git-ignored): `TEST_DATABASE_URL` added. Its password is a test-only local password; never reuse it for anything real.
- Owner sign-off: n/a

### C-008 Portion P1.1: Database connection and migration runner
- Date: 2026-09-23
- Type: portion
- New files:
  - `app/db.py`: `wait_for_db` (retries with doubling pauses 0.5→8 s, 6 tries, 5 s per-attempt timeout, error without password or extra lines); `migrate` (checks every file before touching the DB: names `NNN_lowercase.sql`, numbers 000.. without gaps/duplicates, UTF-8, not empty/comment-only; CRLF normalized before the SHA-256 checksum; advisory lock so only one instance migrates; one transaction per file incl. its `schema_version` row; refuses edited, renamed or deleted applied files; returns names applied); `open_pool` (sync pool, borrow timeout).
  - `migrations/000_schema_version.sql`: the `schema_version` table.
  - `tests/test_db.py`: 36 tests: apply in order, rerun is a no-op, later additions, real directory, `%` in SQL, failure rolls back only the failing file, fix-then-retry, bad 000, edited/renamed/deleted applied files, CRLF vs LF, 11 bad-file cases refused before any DB access, non-UTF-8, non-SQL files and `.sql` folders ignored, **two instances at once apply exactly once**, lock released after failure, wait succeeds/retries/gives up with exact backoff, password never in errors, empty error message, URL without password, real closed port bounded, pool works, **exhausted pool times out cleanly and recovers**.
  - `tests/test_fixtures.py`: 12 tests for the test-database helpers (retry through the autovacuum race for both error types, give up after the deadline, other errors not retried, missing DB fine, cleanup pattern only matches fixture-made names).
- Changed files:
  - `app/main.py`: lifespan: wait for DB → migrate → open pool on startup; close pool on shutdown · depends: every test using `client`/`create_app` now needs a database.
  - `tests/conftest.py`: `TEST_DATABASE_URL` from env or `.env`; `db_url` fixture creates/drops a throwaway database per test; `_drop_database` retries through the autovacuum race (O-003); session-start cleanup of leftover `t_<12 hex>` databases; `env_vars` now points at the throwaway DB.
  - `tests/test_health.py`: +2 tests: startup migrates and opens the pool, shutdown closes it; startup fails when the DB is unreachable.
  - `.env.example`: `TEST_DATABASE_URL` documented.
  - `README.md`: database requirement + automatic migrations.
  - `INSTRUCTION.md` §2: new rules "save full output" and "a single unexplained failure blocks the gate"; §5 prerequisite row marked done.
- Deleted files: none
- Decisions referenced: D-003, D-008, D-009 (proposed)
- Bugs found during the portion:
  1. **Intermittent test error (1 run in ~40)**. Root cause from the PostgreSQL server log: `DROP DATABASE ... WITH (FORCE)` → `permission denied to terminate process`. An autovacuum worker (superuser) had connected to the fresh test database at teardown; our non-superuser test role can't end it. Left one database behind (`t_28df69728aa2`). Fix: bounded retry on exactly `InsufficientPrivilege`/`ObjectInUse` + leftover cleanup + tests. Test-infrastructure bug, not app code. See O-003.
  2. Gate process: the erroring run's traceback was lost because output was piped to `tail`. Fixed in INSTRUCTION.md §2.
  3. Closed-port test took 10 s on Windows (refused connections wait for the full timeout), close to its own limit → flake risk. Reduced to one attempt with bound `CONNECT_TIMEOUT + 3`.
- Gate result (full logs saved for every run):
  - G1: `118 passed`
  - G2/G3: `app\db.py 93 stmts, 26 branches, 100%`; TOTAL 175 stmts, 44 branches, **100%**
  - G4: ruff check: All checks passed; format: 16 files already formatted
  - G5: config-enforced; no new ignores
  - G6: reverse order: 118 passed
  - G7: 5 consecutive runs: 118 passed each; plus 21 clean runs during the investigation; no errors in any saved log
  - Mutation check on `db.py`: **10/10 deliberate bugs caught** (no advisory lock, no per-file transaction, checksum ignored, CRLF not normalized, gaps allowed, password leak, no backoff, missing files ignored, comment-only allowed, renames allowed); restored, 118 passed
  - G8: two real servers started at the same moment on one empty database: both `/healthz` → `{"status":"ok"}`; `schema_version` has `000_schema_version.sql` **once**; no errors in either server log; database dropped afterwards
  - G9: this entry
- `# pragma: no cover` uses: none
- Owner sign-off: **yes (2026-09-23)**, after C-009

### C-009 D-009 cross-platform: CI on Linux, Windows and macOS
- Date: 2026-09-23
- Type: refactor (CI)
- New files: none
- Changed files:
  - `tests/test_ci.py`: changed **first** (4 new requirements failed against the old workflow): runs on all three OSes with `fail-fast: false`; bash on every OS; PostgreSQL 18 via a third-party action **pinned to commit** `c4dda34a…` (v8); no Linux-only service container; tests use a limited `chatbot_test` login created with `NOSUPERUSER`; every non-`actions/` action pinned to a 40-character commit. Now 14 tests.
  - `.github/workflows/ci.yml`: matrix `ubuntu-latest`, `windows-latest`, `macos-latest`; `ikalnytskyi/action-setup-postgres@c4dda34aae1c821e3a771b68b73b13af3198a7ee` with PostgreSQL 18; step creating `chatbot_test LOGIN CREATEDB NOSUPERUSER` (the action's own user is a superuser, which tests must not rely on, O-004); `shell: bash` default; timeout 20 min.
  - `INSTRUCTION.md` P5.2: real-device checks on Android Chrome and iPhone Safari plus desktop browsers.
  - `DECISION.md`: D-009 accepted and expanded; D-007 accepted; C-008 signed off.
- Deleted files: none
- Verified locally: the exact `CREATE ROLE` line from `ci.yml` reaches PostgreSQL's permission check (so the SQL parses); refused only because the local test role can't create roles.
- Gate result (full logs saved): G1 122 passed · G2/G3 100% (175 stmts, 44 branches) · G4 clean after fixing one line-too-long in `tests/test_ci.py` that the gate caught · G6 122 passed · G7 122 passed ×3 · no errors in any log.
- **Not yet proven:** the Windows and macOS runs happen on GitHub after the owner's next push. Owner check (G8): Actions tab shows **3 green jobs** (ubuntu, windows, macos).
- Owner sign-off: yes (2026-09-23): owner's GitHub Actions screenshot shows CI #1 (6e4595c) and CI #2 (f597125) green; each run = 3 jobs (ubuntu, windows, macos) with fail-fast off, so all three passed

### C-010 Portion P1.2: Core schema
- Date: 2026-09-23
- Type: portion
- New files:
  - `migrations/001_init.sql`: 17 tables from PRD §10 (tenants, knowledge_versions, branches, schedules, holidays, events, channels, users, contacts, conversations, messages, bookings, event_registrations, notes, jobs, audit_events, wa_billable) + `set_updated_at` trigger on contacts. **66 check constraints, 21 foreign keys, 12 unique constraints** plus partial/expression unique indexes (one web channel per tenant, case-insensitive email, case-insensitive branch name per tenant, no double booking). Tenant isolation by composite keys (D-010). All timestamps `timestamptz`, money `numeric(10,6)`, no floats, no cascades.
  - `tests/test_schema.py`: 115 tests: shape (all tables, timestamptz only, `created_at` defaults, no floats, exact cost type, tenant index on every tenant table, job-queue index, **every FK is NO ACTION**); 22 invalid tenant values; defaults; knowledge publish gate; schedules incl. boundaries 10/240 min and weekday 1-7; holidays; events; channels (types, external id rule, uniqueness per type, one web per tenant); users (case-insensitive email, role/tenant rule, email format); contacts (uniqueness, phone E.164, **minor can't store a phone**, score/status, JSON shapes, assignee same tenant, `updated_at` trigger); conversations; messages (role, NULL external ids repeat, non-NULL unique per conversation, non-negative tokens/cost, 6-decimal cost); bookings (status, no double booking, rebook after cancel, reminder state); event registrations; notes; jobs; audit events; WhatsApp billing rows; deleting a tenant with data refused, empty tenant allowed; **cross-tenant links refused on every relationship**.
- Changed files:
  - `tests/conftest.py`: `migrated_db_url` = instant copy of a session-wide migrated template (was: migrate per test, ~1 s each); `_run_retrying` shared by drop and clone (autovacuum race on the template → `ObjectInUse`); **session lock** so only the one active test run may delete leftovers, and `OWN_DATABASES` so a run never deletes its own databases; helpers `_new_database_name`, `_create_database`, `_leftovers`, `_url_for`.
  - `tests/test_fixtures.py`: +7 tests (clone retries, copy has every migration, copy changes don't reach the template, second run can't take the lock, lock exclusive and released on close, leftovers exclude own databases, every fixture database registered). Now 19.
  - `app/db.py`: **bug fix**: `open_pool` gets its own `open_timeout` (default `POOL_OPEN_TIMEOUT` = 10 s) instead of reusing the borrow timeout; pool connections get `connect_timeout=5`.
  - `tests/test_db.py`: +3 regression tests (short borrow timeout doesn't limit opening, with a deliberately slow connect; pool open against a dead port fails within `open_timeout + CONNECT_TIMEOUT + 3`; pool connections carry `connect_timeout`); the real-migrations test expects `001_init.sql`. Now 39.
  - `tests/test_health.py`: startup test expects both migrations.
  - `PRD.md` §10: as-built note (extra `tenant_id` columns, composite keys, no cascades).
  - `INSTRUCTION.md` §2: rule "deliberate-bug checks must be crash-safe" (backup outside the project, restore in `finally`, byte-identical check).
- Deleted files: none
- Decisions referenced: D-008, D-009, D-010 (proposed)
- Bugs found during the portion (each: failing test first, then fix):
  1. **App bug, `open_pool`:** one timeout served two purposes, so a short borrow timeout also limited the pool's first connection. Seen as 1 failure in G7 (`PoolTimeout: pool initialization incomplete after 0.3 sec`). Reproduced deterministically with a slowed connect; fixed with a separate `open_timeout`.
  2. **App gap, pool connections had no per-connection timeout:** found while bounding the new dead-database test (5.6 s). Fixed: `connect_timeout=5`. The new test fails without the fix, passes with it.
  3. **Test gap, cascades:** the mutation check added `ON DELETE CASCADE` to branches and no test failed, because other tables still blocked the tenant delete. Fixed with a catalog test requiring every FK to be NO ACTION; it now catches both CASCADE and SET NULL.
  4. **Test-infra risk, concurrent runs:** leftover cleanup would delete another active run's databases. Fixed with the session lock + own-database set; proven by two full runs started 3 s apart (153 passed each).
  5. **My edit mistakes, caught by the gate:** a parametrize decorator left on a helper instead of its test (1 error); import order (lint). Both fixed.
  6. **Process:** the previous session ended mid-mutation-check and left `001_init.sql` missing its no-double-booking index. Detected by an integrity check at the start of this session, restored, verified (114 schema tests passed), and the crash-safe mutation rule added.
- Gate result (full logs saved):
  - G1: `247 passed`
  - G2/G3: `app/db.py` 94 stmts, 26 branches, 100%; TOTAL 176 stmts, 44 branches, **100%**
  - G4: ruff check: All checks passed; format: 17 files already formatted
  - G5: config-enforced; no new ignores
  - G6: reverse order: 247 passed
  - G7: 247 passed ×3; no errors or failures in any saved log; `001_init.sql` unchanged during the gate (SHA-256 OK); 0 leftover test databases
  - Mutation checks on `001_init.sql` (crash-safe, restored byte-identical): **10/10 caught** after adding the FK catalog test (minor phone rule, publish gate, contact and message tenant binding, case-insensitive email, double booking, global audit rule, operator/tenant rule, float cost, cascade; plus SET NULL)
  - G8: real migrated database, every table's columns listed and compared with PRD §10: all present; differences are the deliberate D-010 additions (recorded in PRD §10)
  - G9: this entry
- `# pragma: no cover` uses: none
- Owner sign-off: **yes (2026-09-23)**

### C-011 Portion P1.3: Security helpers
- Date: 2026-09-23
- Type: portion
- New files:
  - `app/security.py`: `encrypt`/`decrypt` (Fernet; `DecryptionError` for wrong key, tampering or garbage, message never contains a key); `hash_password`/`verify_password` (scrypt, NFKC, 12-256 chars via `PasswordPolicyError`, parameters read from each stored hash, malformed or absurd stored hashes → False, overlong attempts → False without hashing, constant-time compare); `verify_meta_signature`; `verify_telegram_secret`; `make_csrf_token`/`check_csrf_token`.
  - `tests/test_security.py`: 86 tests. Encryption: round-trips (empty, Bangla, 10,000 chars, JSON), different ciphertext each time, wrong key, one flipped bit, garbage, key not leaked. Passwords: right/wrong (case, spaces, truncation), random salt, stored format and OWASP parameters, Bangla, NFD vs NFC, old hashes with other parameters still verify, 11/12/256/257-char boundaries, overlong attempt never hashed, 11 malformed stored hashes (incl. non-power-of-two cost, zero block size, absurd cost), constant-time compare used. Meta: valid, uppercase hex, 10 bad headers (missing, no prefix, sha1, short, long, non-hex, non-ASCII, one char off), one-byte body change, wrong or empty secret, empty body. Telegram: exact match only (case, spaces, truncation, Bangla), empty expected, constant-time. CSRF: own session only, other secret, expiry boundary, future tokens vs small skew, edited timestamp, 10 malformed tokens, empty session id, domain-separated key, real clock.
- Changed files: none
- Deleted files: none
- Decisions referenced: D-011 (proposed)
- Bugs found during the portion:
  1. **Test gap found by coverage:** the path where a stored hash has a cost in range but not a power of two (scrypt raises) was untested. Added that case plus zero block size and zero parallelism.
  - Noted by the mutation check: without the strict hex check, a non-ASCII signature header would make `hmac.compare_digest` raise `TypeError`, crashing the webhook instead of rejecting it. The check prevents it and a test guards it.
- Gate result (full logs saved):
  - G1: `333 passed`
  - G2/G3: `app/security.py` 82 stmts, 22 branches, 100%; TOTAL 258 stmts, 66 branches, **100%**
  - G4: ruff check: All checks passed; format: 19 files already formatted
  - G5: config-enforced; no new ignores
  - G6: reverse order: 333 passed
  - G7: 333 passed ×3; no problems in any saved log; `security.py` and `001_init.sql` unchanged during the gate (SHA-256 OK); 0 leftover test databases
  - Mutation check (crash-safe, restored byte-identical): **13/13 caught** (non-constant-time compare, no NFKC, length off by one, weaker scrypt cost, overlong guard removed, decrypt swallowing errors, Meta: empty secret, missing prefix check, missing hex/length check; Telegram: whitespace stripped; CSRF: not session-bound, future tokens, expiry off by one)
  - G8: none (pure functions, per INSTRUCTION.md)
  - G9: this entry
- `# pragma: no cover` uses: none
- Owner sign-off: yes (2026-09-23), by asking to go to P2.0

### C-012 P1.3 revised: owner's password and CSRF rules (D-011)
- Date: 2026-09-23
- Type: fix (requirements change by owner)
- New files: none
- Changed files:
  - `tests/test_security.py`: changed **first** (18 new-rule tests failed against the old code). Password tests rewritten for 8-256 characters, ASCII only, uppercase + lowercase + digit + symbol: exact 8 and 256 accepted, 7 and 257 rejected, each rule alone, space is not a symbol, every ASCII symbol accepted, 8 non-ASCII cases rejected (Bangla, Bangla digit, emoji, accented, tab, newline, NUL, non-breaking space), non-ASCII digits (Bangla, Arabic-Indic, full-width) don't satisfy the number rule, all problems reported together, non-ASCII login attempts fail cleanly; Bangla/NFKC tests removed (no longer allowed); CSRF lifetime pinned to 8 hours. Now 107 tests.
  - `app/security.py`: `check_password_policy` (all rules, lists every broken one); `PASSWORD_MIN` 12 → 8; `PASSWORD_CHARS` printable ASCII; NFKC normalization removed; `CSRF_MAX_AGE` 12 h → 8 h. Hashing parameters unchanged (OWASP).
  - `DECISION.md`: D-011 accepted with the owner's values.
- Deleted files: none
- Decisions referenced: D-011 (accepted)
- Bugs found:
  1. **My edit mistake:** raw tab, newline, NUL and non-breaking-space characters landed in the test file instead of escape sequences (the newline split a string, a syntax error), plus a stray `\:` escape. Found by `grep` reporting the file as binary; lines rewritten and the file checked for control characters and parsed.
  2. **Test gap found by the mutation check:** letting a Bangla digit count as "a number" went unnoticed because the ASCII-only rule already rejected that password. Added a test that the number rule holds on its own (Bangla, Arabic-Indic, full-width digits); now caught.
- Gate result (full logs saved):
  - G1: `354 passed`
  - G2/G3: `app/security.py` 97 stmts, 34 branches, 100%; TOTAL 273 stmts, 78 branches, **100%**
  - G4: ruff check: All checks passed; format: 19 files already formatted
  - G5: config-enforced; no new ignores
  - G6: reverse order: 354 passed
  - G7: 354 passed ×3; no problems in any saved log; `security.py` and `001_init.sql` unchanged during the gate; 0 leftover test databases
  - Mutation check (crash-safe, restored byte-identical): **18/18 caught** (compare not constant-time, min 7, max 257, non-ASCII allowed, no uppercase rule, no lowercase rule, Bangla digit counts as number, space counts as symbol, weaker scrypt, overlong guard removed, decrypt swallows errors, Meta: empty secret, no hex/length check; Telegram strips whitespace; CSRF: not session-bound, future tokens, 12 h lifetime, expiry off by one)
  - G9: this entry
- Note: full gate run time is now ~4 min (O-006 threshold is 5 min).
- `# pragma: no cover` uses: none
- Owner sign-off: yes (2026-09-23), by asking to go to P2.0

### C-013 Password hashing memory: 128 MiB → 16 MiB per login (same OWASP strength)
- Date: 2026-09-23
- Type: fix (resource risk)
- Why: at N=2^17, r=8, p=1 each login needed 128 MiB of RAM, so ~5 simultaneous staff logins could exhaust a 512 MB-1 GB container and crash the server. OWASP lists N=2^14, r=8, p=5 as an equivalent setting. Measured locally: 16 MiB and ~0.5 s per login (was 128 MiB and ~0.8 s).
- New files: none
- Changed files:
  - `tests/test_security.py`: changed **first** (2 tests failed against the old value): stored-hash parameters must be (2^14, 8, 5); new test that one login uses at most 16 MiB. Now 108 tests. Existing hashes made with other parameters still verify (unchanged test).
  - `app/security.py`: `SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 5` with the reason in a comment.
  - `DECISION.md`: D-011 updated.
- Deleted files: none
- Decisions referenced: D-011
- Bugs found: **my edit mistake**: the new test was inserted in the middle of an existing one, moving its last line (`assert PASSWORD not in stored`) into the new test (TypeError). Moved back; both pass.
- Gate result (full logs saved):
  - G1: `355 passed`
  - G2/G3: TOTAL 273 stmts, 78 branches, **100%**
  - G4: ruff check: All checks passed; format: 19 files already formatted
  - G6: reverse order: 355 passed
  - G7: 355 passed ×3; no problems in any saved log; `security.py` and `001_init.sql` unchanged during the gate; 0 leftover test databases
  - Mutation check (crash-safe, restored byte-identical): **19/19 caught**, incl. the new "weaker cost (p=1)" and "back to 128 MiB per login"
  - G9: this entry
- `# pragma: no cover` uses: none
- Owner sign-off: yes (2026-09-23), by asking to go to P2.0

### C-014 Migration 002: universal core, performance log, minors' phones (+ PC crash recovery)
- Date: 2026-09-23
- Type: refactor (schema upgrade) + docs
- New files:
  - `migrations/002_universal_core.sql`: `tenants.industry` (default `study_abroad`, format-checked); `contacts.status` → generic stages `new, contacted, qualified, booked, in_progress, won, lost` with old values mapped (counselling_booked → booked, counselled/applied → in_progress, enrolled → won); drops the minor-phone rule (D-014); new `bot_turns` performance table (D-013) with its rules and indexes; moves existing AI usage from `messages` into `bot_turns` (button answers recorded as `quick` with no model); drops usage columns from `messages`. `001_init.sql` untouched.
  - `tests/test_migration_002.py`: 5 upgrade-path tests on a database at 001 filled with old-style rows: every old stage mapped correctly, no contact or message lost, usage moved exactly (incl. `quick` rows), `messages` content-only, existing tenants get `study_abroad`.
- Changed files:
  - `tests/test_schema.py`: now 138 tests: `bot_turns` in the table list; exact-cost check moved to `bot_turns`; old consultancy stages rejected, all 7 generic stages accepted; minor's phone stored (D-014); messages hold content only; `bot_turns`: full row, 13 invalid cases (source, channel, language, negative times/tokens/cost, AI reply without model, paid button answer, overlong error code), button answer without model, tenant binding, survives deletion of its message, no free-text columns beyond the 6 short metadata fields; `industry` default and format.
  - `tests/test_db.py`, `tests/test_fixtures.py`, `tests/test_health.py`: expect `002_universal_core.sql` among applied migrations.
  - `PRD.md` (v2.2): new §0 universal core + industry packs; §5.2 and minors paragraph; §5.3 marked as study_abroad pack rules; §10 as-built note for 002; §12.3 and §17 risk updated; Appendix A prompt and Appendix C minor case updated.
  - `INSTRUCTION.md`: new portion **P2.0 industry pack loader** (first in Level 2) and the rule that Levels 2-7 read industry rules from packs; P2.3, P4.3, P7.1 updated; new gate rules: capture stderr and exit codes; after-crash checklist.
  - `DECISION.md`: D-012, D-013, D-014 accepted; O-008 lawyer review.
- Deleted files: none
- Decisions referenced: D-010, D-012, D-013, D-014
- **PC crash during the work** (while the database tests were running):
  1. `tests/test_migration_002.py` was left as 5,081 zero bytes (space reserved, content never written). Restored from the exact text written earlier in the session; checked: no NUL bytes, parses.
  2. All other project files scanned: no damage. `app/security.py` and `migrations/001_init.sql` matched their saved SHA-256 fingerprints. `.coverage` (binary), empty `__init__.py` files and `dependency_links.txt` are empty/binary by design.
  3. PostgreSQL service came back running; no leftover test databases.
  4. **The crash also corrupted `.ruff_cache`** (package root recorded as blank bytes). Ruff then panicked on every file in `tests/` and reported nothing on stdout. **My earlier "lint clean" statement after the crash was wrong**: my command didn't capture stderr. Found by the saved G4 log (blank summary, 10 files instead of 20). Fixed by deleting `.ruff_cache` and `__pycache__`; the real lint run then found 6 line-too-long findings and 1 unformatted file in `tests/test_migration_002.py`, now fixed. New INSTRUCTION.md rules prevent a repeat.
- Gate result (full logs saved, stdout + stderr, exit codes):
  - G4: ruff check exit 0 (All checks passed!); format exit 0 (20 files already formatted); no panics or warnings in either log
  - G1: exit 0, `383 passed`
  - G2/G3: TOTAL 273 stmts, 78 branches, **100%**
  - G6: reverse order: 383 passed
  - G7: 383 passed ×3
  - No problems in any saved log; no source, test or migration file changed during the gate; 0 leftover test databases
  - Mutation check on `002_universal_core.sql` (crash-safe, restored byte-identical): **12/12 caught** (wrong stage mapping ×2, missing `in_progress`, unchecked industry name, AI reply without model, paid button answer, unchecked error length, bot_turns not tenant-bound, usage not moved, button answers recorded as AI, usage columns kept on messages, negative latency)
  - G9: this entry
- `# pragma: no cover` uses: none
- Owner sign-off: yes (2026-09-23), by asking to go to P2.0

### C-015 Portion P2.0: Industry pack loader
- Date: 2026-09-23
- Type: portion
- New files:
  - `app/packs.py`: `load_pack(name, packs_dir)` reads `packs/<name>/` (`pack.toml`, `prompt.md`, `knowledge_template.md`) with stdlib `tomllib` and validates everything, **listing every problem at once**; returns an immutable `Pack` (fields, stage labels, scoring rules as `Condition`/`Flag` objects, tenant settings, prompt, knowledge template). Checks: pack name format **before touching disk** (blocks `../` path escapes), name = folder, required files, UTF-8, valid TOML, unknown keys anywhere (typo catcher), display name, version; all 7 generic stages with an `en` label and valid language codes; field names, types (`text/int/bool/choice/list/yearmonth`), priorities, labels, choices (only on choice fields, non-empty, unique), no shadowing of built-ins `phone`/`name`/`adult`; scoring `hot`/`warm` required, conditions refer to real fields, op allowed for the field's type, right arguments (`value`/`values`/`months` 1-120/`setting`), values must be real choices / true-false / whole numbers (true is not a number), `any` groups, flags unique and well-formed, referenced tenant settings declared; prompt placeholders only `{{business_name}}` and `{{knowledge_markdown}}` (required), no malformed `{{`/`}}`; knowledge template not empty. Evaluating the rules is P2.3.
  - `packs/study_abroad/pack.toml`: 13 fields (PRD §5.2), Hot/Warm rules and 3 flags (PRD §5.3), English + Bangla stage labels, tenant setting `served_countries`.
  - `packs/study_abroad/prompt.md`, `packs/study_abroad/knowledge_template.md`: extracted from PRD Appendix A/B by script (so they match the PRD), `{{consultancy_name}}` → `{{business_name}}`.
  - `tests/fixtures/packs/pet_care_sample/` (3 files): a small second industry proving the core isn't study-abroad-only; also the base for every broken-pack test.
  - `tests/test_packs.py`: 97 tests: real study_abroad pack loads (fields, stages in English and Bangla, rules, flags, placeholders, settings); pet-care pack loads (Bangla survives); equal on reload; immutable; nested `any`; 9 bad pack names incl. `../secrets`; missing folder; each missing file named; name/folder mismatch; invalid TOML; non-UTF-8; unknown keys; bad display name/version; stage missing/unknown/no `en`/empty/bad language code; field type, duplicate, built-in shadowing ×3, name format ×4, choices missing/empty/duplicate/on non-choice fields, priority, typo'd key, `en` label, no fields; rules on unknown fields, unknown ops, wrong choices, 12 bad argument cases, undeclared setting, wrong field type for an op, empty/mixed `any`, missing `warm`, duplicate/badly named flags, empty `when`, setting types; prompt placeholder required/unknown/malformed ×3/empty; empty knowledge template; every problem listed; plus 15 wrong-shape cases (text where a table is expected, etc.) and 7 value-type cases.
- Changed files: none (DECISION.md: this entry, sign-offs, open items)
- Deleted files: none
- Decisions referenced: D-012
- Bugs found:
  1. **Loader bug, found by the tests:** a field with a misspelled type (e.g. `"boolean"`) was reported, but any scoring rule using that field then crashed the loader with `KeyError` instead of a clean message. Fixed; a mutation check confirms the tests catch the crash if the guard is removed.
  2. **Coverage found 19 untested lines** (wrong-shape input: text where a table was expected, etc.). Added 22 tests; now 100%.
  3. **Windows console encoding:** printing Bangla while output was redirected crashed with `UnicodeEncodeError` (cp1252). Not a loader bug, but a future-logging risk: see O-009.
- Gate result (full logs saved, stdout + stderr, exit codes):
  - G4: ruff check exit 0; format exit 0 (26 files already formatted)
  - G1: exit 0, `480 passed`
  - G2/G3: `app/packs.py` 294 stmts, 150 branches, 100%; TOTAL 567 stmts, 228 branches, **100%**
  - G6: reverse order: 480 passed
  - G7: 480 passed ×3; no problems in any saved log; no source, test or pack file changed during the gate; 0 leftover test databases
  - Mutation check (crash-safe, restored byte-identical): **15/15 caught** (pack-name check removed/path escape, name-folder mismatch, unknown keys allowed, choice values unchecked, undeclared setting, built-in shadowing, `en` label optional, missing stage, knowledge placeholder optional, malformed placeholder, months 121, bool unchecked, true counts as a number, bad-type guard removed, only first problem reported)
  - G8: study_abroad pack loaded and printed: 13 fields; stages in English and Bangla (Bangla verified in the UTF-8 output file); Hot = phone present AND intake within 9 months AND (English score present OR test is MOI/booked) AND funding ≠ scholarship-only AND a target country the consultancy serves; Warm = phone AND target country AND intake within 18 months; flags refusal, long_gap, scholarship_only; matches PRD §5.3
  - G9: this entry
- `# pragma: no cover` uses: none
- Owner sign-off: yes (2026-09-23), by asking to go to P2.1 ("ok g 2.1"); hot/warm scoring confirmed: "keep it"

### C-016 Portion P2.1: Phone normalization
- Date: 2026-09-23
- Type: portion
- New files:
  - `app/phones.py`: `normalize_phone(text, country="BD")` → E.164 (`+8801712345678`) or `None`; never raises on user input (only `ValueError` for an unsupported tenant country, a configuration error). Accepts `+`, `00` and no-plus-with-country-code forms, local numbers with the trunk 0 dropped; separators space, `-`, `.`, `(`, `)`; digits in any script (Bangla, Devanagari, full-width...) via `unicodedata.decimal` (superscripts rejected); input over 64 characters rejected; `+` only at the start. Bangladesh: mobile must be `+880 1[3-9]` + 8 digits (landlines rejected) and local numbers must start with 0 (no guessing). Other countries: calling-code table for BD, NP, IN, PK, LK, NG, MY, AE, SA, GB, US, CA, AU with national-number lengths; unknown codes follow general E.164 rules (8-15 digits, not starting with 0). `+880` numbers get Bangladesh rules whatever the tenant's country. Numbers inside sentences are not extracted (the AI passes only the number).
  - `tests/test_phones.py`: 79 tests: 16 formats of one BD mobile (incl. Bangla, mixed and full-width digits), all 7 operator prefixes, 11 invalid BD numbers (012/010/011, short, long, landlines, no leading 0), 20 junk inputs (None, empty, letters, emoji, sentences, two numbers, double/misplaced plus, slash, underscore, hash, superscripts with and without leading 0, non-strings, 10,000 zeros), 8 other-country cases (Nepal with Devanagari digits, UK, Pakistan, India, US), +880 rules at a foreign tenant, local number follows the tenant's country, international length/start rules, 15 vs 16 digits outside the table, 64-character limit, 4 unsupported countries, calling-code table consistency; **4 hypothesis property tests** (any text never raises; phone-like text never raises; accepted numbers normalize to themselves; every valid BD mobile survives any separator and Bangla digits).
- Changed files:
  - `tests/conftest.py`: hypothesis profile `gate` (D-004): `derandomize=True`, `deadline=None`, `max_examples=500`, loaded for every run.
- Deleted files: none
- Decisions referenced: D-004, D-012 (international readiness PRD §19.1)
- Bugs found:
  1. **Wrong test expectation (mine):** I first expected `01712345678` at a UK tenant to be rejected; under UK rules it's a valid-looking UK number. Corrected to what matters: it's never turned into a Bangladeshi number.
  2. **Mutation check found 2 test gaps** (the implementation was right; the tests didn't isolate the rule): superscript digits were only tested in a form another rule already rejected; the 15-digit limit was only tested with a `+1` number that the US rule rejected first. Added isolated tests; both now caught. Also added a test isolating the 64-character guard before running the check.
- Gate result (full logs saved, stdout + stderr, exit codes):
  - G4: ruff check exit 0; format exit 0 (28 files already formatted)
  - G1: exit 0, `559 passed`
  - G2/G3: `app/phones.py` 51 stmts, 30 branches, 100%; TOTAL 618 stmts, 258 branches, **100%**
  - G6: reverse order: 559 passed
  - G7: 559 passed ×3 (hypothesis derandomized: same inputs every run); no problems in any saved log; nothing changed during the gate; 0 leftover test databases
  - Tests also pass without UTF-8 mode (the gate's plain Windows mode), so the Bangla test inputs don't hit O-009.
  - Mutation check (crash-safe, restored byte-identical): **14/15 caught + 1 equivalent mutant**. Caught: 012 accepted, BD local without 0 guessed, superscripts as digits, ASCII-only digits, `_`/`/` allowed, 64-character guard removed, `+` anywhere, `00` not understood, `880` without `+` not understood, trunk 0 kept, leading 0 after `+`, 16 digits, unknown country silently BD, BD rule skipped. **Equivalent (can't change behaviour, no test possible):** widening the BD national length to 10-11, because the BD mobile pattern already requires exactly 10 digits.
  - G8: none (pure function, per INSTRUCTION.md)
  - G9: this entry
- `# pragma: no cover` uses: none
- Owner sign-off: yes (2026-09-23), by approving the next plan ("g")

### C-017 Portion P1.4: Migration 003 (contact email, tenant settings, quick answers + history)
- Date: 2026-09-23
- Type: portion (data layer addition, D-015)
- New files:
  - `migrations/003_quick_answers_and_contact_details.sql`: `contacts.email` (format + ≤ 254 characters); `tenants.settings` (JSON object); SQL check functions for answers (2-letter language → non-empty text), triggers (non-empty, trimmed, lower-case) and button codes; `quick_answers` table (code per tenant unique, must have an answer or an action, `updated_at` trigger); trigger function `quick_answers_unique_triggers` (no phrase twice in a row, no phrase shared by two quick answers of one company, inactive rows still reserve phrases, per-company advisory lock so two admins saving at once are serialized); `quick_answer_history` with trigger `quick_answers_history` writing before/after/who (`app.user_id`)/when on every insert, update and delete, kept after deletion (no FK to the quick answer) so changes can be undone.
  - `tests/test_migration_003.py`: 48 tests: valid/invalid emails incl. 254-character boundary, email optional; settings default and shape; quick answer defaults; 6 bad codes; code unique per company only; 10 invalid rows (answers shape, empty/non-text answer, bad language code, unknown action, empty/untrimmed/upper-case trigger, empty button); action-only row; Bangla trigger and answer; phrase clash on insert and on update; duplicate phrase in one row; editing a row keeps its own phrases; same phrase in two companies; inactive rows reserve phrases; **two admins saving the same phrase at once (second waits, then is rejected)**; history of create/update/delete with exact before/after; history survives deletion; who changed it (with and without a user); history carries the company; `updated_at` moves; deleting a company with quick answers refused.
- Changed files:
  - `tests/test_db.py`, `tests/test_health.py`, `tests/test_fixtures.py`: expect `003_quick_answers_and_contact_details.sql`.
  - `tests/test_schema.py`: table list includes `quick_answers`, `quick_answer_history` (so the all-FKs-NO-ACTION, timestamptz, tenant-index and no-float checks cover them).
  - `PRD.md` §6.8 F47 and §10; `INSTRUCTION.md` P1.4, new P2.1b, P2.2 rewritten for database quick answers; `DECISION.md` D-015, O-012.
- Deleted files: none
- Decisions referenced: D-010, D-012, D-015
- Bugs found: none (all new tests passed first run; the mutation check below confirms they bite). One lint finding (long docstring) fixed.
- Gate result (full logs saved, stdout + stderr, exit codes):
  - G4: ruff check exit 0; format exit 0 (29 files already formatted)
  - G1: exit 0, `607 passed`
  - G2/G3: TOTAL 618 stmts, 258 branches, **100%** (SQL-only portion; Python coverage unchanged)
  - G6: reverse order: 607 passed
  - G7: 607 passed ×3; no problems in any saved log; nothing changed during the gate; 0 leftover test databases
  - Mutation check (crash-safe, restored byte-identical): **16/16 caught** (email length, settings shape, answer language code, empty answer, upper-case and untrimmed triggers, answer-or-action rule, code uniqueness, cross-row clash, **lock between admins removed**, row clashing with itself on update, other companies' phrases colliding, duplicate in one row, history skipping deletes, history losing the "before", history ignoring who)
  - G9: this entry
- `# pragma: no cover` uses: none
- Owner sign-off: yes (2026-09-24), "g" to continue to P2.1b

### C-018 Portion P2.1b: Contact-detail checks (international)
- Date: 2026-09-24
- Type: portion (D-015)
- New files:
  - `app/contact_details.py`: `normalize_email` (trim; exactly one `@`; ASCII local part ≤ 64 with dot rules; domain lower-cased and IDNA-encoded, e.g. `münchen.de` → `xn--mnchen-3ya.de`; every label checked; alphabetic or IDN top-level domain; ≤ 254 total; result always satisfies the database's email rule); `normalize_name` (NFC, collapse spaces, 1-100 characters, letters of any script plus marks, `. ' - ’`, and the Bangla zero-width joiners; digits, emoji, symbols and letter-less names rejected); `normalize_country` (all 249 ISO 3166-1 alpha-2 codes, plus English and Bangla common names of source and study-destination countries, e.g. UK/England → GB, বাংলাদেশ → BD); `normalize_year_month` ("2027-01", "01/2027", "Jan 2027", "2027 Jan", "জানুয়ারি ২০২৭", "২০২৭-০৯" → "2027-01"; years 2000-2100; months 1-12; rejects two-digit years, full dates, extra words); `valid_timezone` (exact IANA names via `zoneinfo`); `normalize_https_url` (https only, real host (IDNA), no credentials, no spaces or control characters, ≤ 2048, valid port; scheme and host lower-cased; path, query and fragment kept).
  - `tests/test_contact_details.py`: 220 tests: 8 valid and 37 invalid emails (incl. 254-character boundary and a 258-character case), 11 valid and 21 invalid names, Bangla joiners kept, name length boundary, 22 valid and 18 invalid countries, 17 valid and 24 invalid year-months, 5 valid and 17 invalid timezones (incl. path traversal), 7 valid and 25 invalid URLs; **5 hypothesis properties** (never raises; accepted values are stable; accepted emails satisfy the database rule; names/year-months well formed).
- Changed files:
  - `pyproject.toml`: `tzdata==2026.4` (D-016).
  - `INSTRUCTION.md`: P2.1b added in the earlier docs change (C-017).
- Deleted files: none
- Decisions referenced: D-004, D-015, D-016
- Bugs found:
  1. **Wrong test (mine):** the "over 254 characters" email was only 249; corrected to 258.
  2. **Raw invisible characters** (U+200C/U+200D) were written into the source and a test instead of `\u200c`/`\u200d` escapes; found with a byte scan and replaced, so nothing invisible remains in the code.
  3. **Coverage found an untested line** (URL `#fragment`); tests added.
  4. **Mutation check found redundant code:** converting other scripts' digits to ASCII before parsing month/year was unnecessary, because Python's `\d` and `int()` already handle Bangla and other digits (`int("২০২৭")` → 2027). Removed.
  - The mutation harness printed decode errors reading pytest output (Windows cp1252 vs UTF-8, O-009); results come from exit codes and are valid.
- Gate result (full logs saved, stdout + stderr, exit codes):
  - G4: ruff check exit 0; format exit 0 (31 files already formatted)
  - G1: exit 0, `827 passed`
  - G2/G3: `app/contact_details.py` 112 stmts, 46 branches, 100%; TOTAL 730 stmts, 304 branches, **100%**
  - G6: reverse order: 827 passed
  - G7: the first gate run was cut off when the session ended, after G1-G6 had passed. After-crash checklist: no damaged files, all files identical to the gate's start (SHA-256), caches cleared, 1 leftover test database (from the interruption) cleaned automatically. Then G7: 827 passed ×3, no problems in any log, no file changed.
  - Mutation check (crash-safe, restored byte-identical): **18/19 caught**; the 1 miss was the redundant digit conversion, now deleted (email: two `@`, dots anywhere in the local part, local part 65, domain not lower-cased, numeric TLD; name: no NFC, digits allowed, letter-less names, Bangla joiners rejected, 101 characters; country: case-sensitive aliases; year-month: 1999, month 13; timezone: case-insensitive; URL: http, credentials, spaces, fragment dropped)
  - G8: none (pure functions)
  - G9: this entry
- Note: full test run now takes 4-6.5 minutes (O-006 threshold of 5 minutes reached).
- `# pragma: no cover` uses: none
- Owner sign-off: **signed off** 2026-09-24 ("G p2.2")

### C-019 Test speed-up (O-006)
- Date: 2026-09-24
- Type: test infrastructure (D-017)
- New files: none
- Changed files:
  - `pyproject.toml`: `pytest-xdist==3.8.0` (dev), `-n auto` in addopts, coverage `patch = ["subprocess"]`.
  - `tests/conftest.py`: leftover cleanup + session lock moved from a session fixture to `pytest_configure`/`pytest_unconfigure` in the **main process only**, so a parallel worker can never drop another worker's databases. `migrated_db_url` now reuses a per-worker copy: after each test it ends connections the test left open, compares a schema fingerprint (tables, columns, defaults, constraints, indexes, triggers, functions, types, enums, permissions, database settings, applied migrations) with the template, then TRUNCATEs every table except `schema_version` and restarts sequences. Fingerprint differs or reset fails → the copy is dropped and the next test gets a fresh clone.
  - `tests/test_fixtures.py`: +18 tests: only the main process cleans up; reset empties every table but keeps migrations; IDs restart at 1; 11 kinds of structure change detected; changed database setting detected; a connection left holding a table lock is ended; seed really creates quick-answer history; a reused copy starts empty.
  - `tests/test_config.py`: the random "truncated Fernet key" parameter got a fixed id (`truncated`).
- Deleted files: none
- Decisions referenced: D-004, D-017, O-006
- Bugs found:
  1. **Found by xdist:** a test parameter was a random key, so the test's name changed on every collection; parallel workers refused to run (they must collect identical tests). Fixed with a fixed id.
  2. **My first reset used DELETE:** deleting quick answers fired the history trigger, which re-inserted history rows and broke the tenant foreign key. Switched to TRUNCATE (fires no row triggers); regression test added.
  3. **A failed reset left a dirty copy** that failed the next 290 tests; the fixture now drops the copy whenever a reset fails or raises.
  4. **My own edit** cut off the last three fixtures of conftest.py; ruff caught it (unused imports) and they were restored exactly.
  - Session crashed mid-work: after-crash checklist run (no damaged files, caches cleared, 2 leftover databases cleaned automatically).
- Gate result:
  - G4: ruff check exit 0; format exit 0 (31 files)
  - G1: 845 passed, serial 3:25 (was 4:49), **parallel 1:41**
  - G2/G3: TOTAL 730 stmts, 304 branches, **100%** (workers included)
  - G6: reverse order: 845 passed (1:51)
  - G7: 845 passed ×3 (1:40, 1:51, 1:46), no problems in logs, 0 leftover databases
- `# pragma: no cover` uses: none
- Owner sign-off: **signed off** 2026-09-24 ("G p2.2")

### C-020 Portion P2.2: Quick answers from the database + knowledge versions
- Date: 2026-09-24
- Type: portion (D-015)
- New files:
  - `app/quick_answers.py`: `normalize_trigger` (one normalization for saved triggers and student text: NFKC + casefold, letters/marks/digits of any script kept, punctuation/emoji → space, Bangla joiners ignored, ≤ 100 characters); `find_quick_answer` (button payload → exact code, typed text → exact trigger, active only, this tenant only, student's language → English → first alphabetically; no fuzzy matching); `save_quick_answer` (create/replace, lists every problem, buttons must name existing codes, friendly clash/duplicate messages); `delete_quick_answer`; `undo_change` (create → delete, edit → revert, delete → re-create with the same id; only the latest change of an answer can be undone, per-tenant lock so two admins can't undo at once; the undo is itself recorded). Who made the change goes to the history via `app.user_id`, set only for that transaction.
  - `app/knowledge.py`: knowledge versions (`save_version` drafts, `publish_version` only after evals pass and every template blank is filled; publishing an older version rolls back), `published_knowledge`, `estimate_tokens`, `unfilled_blanks`, `render_system_prompt` (byte-identical for the same inputs, Windows line endings included; one-pass fill so knowledge text is never treated as a placeholder).
  - `tests/test_quick_answers.py` (53 tests, 136 cases incl. 2 hypothesis properties: stable/never raises, and every normalized trigger passes the database's own rule), `tests/test_knowledge.py` (23 tests, 41 cases).
- Changed files: none
- Deleted files: none
- Limits chosen (easy to change): 3 follow-up buttons (WhatsApp shows no more), 2000 characters per answer (Messenger's limit), 50 triggers per answer.
- Decisions referenced: D-010, D-012, D-015
- Bugs found:
  1. **The file-writing tool turned `‌`/`‍`/`́` escapes into real invisible characters** (same as P2.1b); found by a scan and replaced with escapes.
  2. **Two of my tests were wrong:** they called the functions on an idle connection, where psycopg commits the function's own transaction, so "rolls back with the caller" and "second admin waits" weren't really tested. Fixed (outer transaction opened first), and a test added for the idle case.
  3. **Mutation check found a third test gap** of the same kind ("two publishes in one transaction"); fixed, mutant now caught.
- Gate result (full logs saved, stdout + stderr, exit codes):
  - G4: ruff check exit 0; format exit 0 (35 files)
  - G1: 1022 passed (2:00)
  - G2/G3: `app/quick_answers.py` 175 stmts / 78 branches, `app/knowledge.py` 47 / 16, both 100%; TOTAL 952 stmts, 398 branches, **100%**
  - G6: reverse order: 1022 passed
  - G7: 1022 passed ×3 (2:00, 2:05, 2:04); no problems in logs; no file changed since the gate started; 0 leftover databases
  - Mutation check (crash-safe, restored byte-identical): **24/25 caught** after the test fix. 1 equivalent: removing `sorted()` in the language fallback changes nothing because PostgreSQL's jsonb already keeps 2-letter keys in alphabetical order; `sorted()` kept so the code doesn't depend on that storage detail.
  - G8 manual check: demo tenant: create (Bangla answer to "Koto taka?"), edit (falls back to English), delete (no match → AI), undo (back); history shows all 4 changes with who; knowledge published and prompt rendered, identical with Windows line endings.
- `# pragma: no cover` uses: none
- Owner sign-off: **signed off** 2026-09-24 ("G")

### C-021 Core stay-on-topic rules for every industry (D-018)
- Date: 2026-09-24
- Type: change to P2.2 code + plan
- New files: none
- Changed files:
  - `app/knowledge.py`: `CORE_RULES`, appended by `render_system_prompt` after every pack's prompt (still byte-identical, one-pass fill).
  - `tests/test_knowledge.py`: +4 tests: both packs end with the core rules; the rules name code, algorithms, homework, essays, translations and "ignore"; a pack whose prompt says "help with anything, including code" still gets the rules after it.
  - `INSTRUCTION.md`: P4.4 reply guard, off-topic streak, daily cap + abuse manual check; P7.1 core off-topic/abuse eval set.
  - `PRD.md`: §9.5 Scope rewritten for every industry; Appendix C +3 abuse eval cases.
- Deleted files: none
- Bugs found: my edit script wrote real line breaks instead of `
` into two test strings; lint caught the syntax error and it was fixed with explicit escapes.
- Gate result: G4 exit 0 (35 files); G1 1026 passed; G2/G3 `app/knowledge.py` 49 stmts / 16 branches 100%, TOTAL 954 / 398 **100%**; G6 1026 passed; G7 1026 passed ×3 (2:03, 2:09, 2:04); no problems in logs; no file changed; 0 leftover databases.
- `# pragma: no cover` uses: none
- Owner sign-off: **signed off** 2026-09-24 ("G")

### C-022 Grounded, short answers in the core rules + token/guard plan (D-019)
- Date: 2026-09-24
- Type: change to P2.2 code + plan
- New files: none
- Changed files:
  - `app/knowledge.py`: `CORE_RULES` also require facts only from <knowledge> (else `log_unanswered`, never guess) and 1-4 sentence answers, for every industry.
  - `tests/test_knowledge.py`: +2 tests (grounding/brevity lines present; core rules stay under 500 estimated tokens).
  - `INSTRUCTION.md`: new portion P2.6 abuse guards; P4.1 12-message history, 1,000-char cap, compact tool JSON, cache layout; P4.2 token settings; P4.4 uses the guards.
  - `PRD.md`: F8 (1,000 chars, 60 AI replies/day), §9.1 (`max_tokens` 500, temperature), §9.2 token budget per turn.
- Deleted files: none
- Gate result: G4 exit 0 (35 files); G1 1028 passed; G2/G3 `app/knowledge.py` 49 / 16 100%, TOTAL 954 / 398 **100%**; G6 1028 passed; G7 1028 passed ×3 (1:56, 1:56, 1:53); no problems in logs; no file changed; 0 leftover databases.
- `# pragma: no cover` uses: none
- Owner sign-off: **signed off** 2026-09-24 ("G")

### C-023 Portion P2.3: Lead scoring
- Date: 2026-09-24
- Type: portion
- New files:
  - `app/scoring.py`: `score(pack, profile, settings, today) -> Score(level, flags)`. Evaluates the pack's hot/warm rules and flags with the generic operators (present, absent, eq, ne, in, not_in, gte, lte, within_months, overlaps_setting, any); no industry rules in code. Text compares ignoring case and extra spaces; numbers/booleans strictly (True ≠ 1); a list or dict where one value belongs matches nothing. Intake: not passed (this month still counts), and its first day at most N months from today (month-end days clamp, leap years handled). `today` must be a date (the caller passes the tenant's local date; the clock is never read). Bad values never raise.
  - `tests/test_scoring.py`: 117 cases: every Hot rule on its own; MOI/booked count as English; unknown funding doesn't block Hot; country matching ignores case; missing served-countries setting blocks Hot; date boundaries (exactly 9 months, +1 day, exactly 18 months, +1 day, this month, passed, Nov → Aug, 31st → Feb 28/29); Warm/Cold; no phone never above Cold; every flag incl. gap 5 vs 4; the pet-care pack scored by the same engine; every operator on hand-built rules; 3 hypothesis properties (never raises on any profile, including when every rule is reached).
- Changed files: `PRD.md` F2: last 30 → 12 messages (was stale after D-019).
- Deleted files: none
- Decisions made here: an unknown value counts as "not equal" (so unknown funding doesn't block Hot); an intake in the current month is upcoming, not past.
- Decisions referenced: D-012, D-019
- Bugs found:
  1. **Real bug found while reviewing:** a list or dict in a single-value field (bad AI output) crashed scoring (unhashable). The first property test missed it because rules stop at the first failed check; added a property test that starts from a Hot profile so every rule runs, and fixed the comparison.
  2. **Mutation check found redundant code:** a "value present" check before eq/in comparisons never changed a result (the loader forbids blank comparison values). Removed.
  3. **Mutation check found a test gap caused by CPython sharing small numbers:** a broken number comparison still matched 5 == 5 by accident; added a test with a large number built at runtime.
- Gate result (full logs saved):
  - G4: ruff check exit 0; format exit 0 (37 files)
  - G1: 1145 passed
  - G2/G3: `app/scoring.py` 75 stmts / 34 branches 100%; TOTAL 1029 / 432 **100%**
  - G6: reverse order: 1145 passed
  - G7: 1145 passed ×3 (1:55, 2:00, 1:57); no problems in logs; no file changed; 0 leftover databases
  - Mutation check (crash-safe, restored byte-identical): **20/20 caught** after the fixes above
  - G8: none (pure function)
- `# pragma: no cover` uses: none
- Owner sign-off: **signed off** 2026-09-24 ("g")

### C-024 Portion P2.4: Appointment slots and bookings (+ neutral names, backslash rule)
- Date: 2026-09-24
- Type: portion (D-020)
- New files:
  - `app/booking.py`: `list_slots` (next open slots from each branch's weekly schedule in the company's timezone; holidays, past and full slots removed; overlapping schedule rows give one slot with the larger capacity; branch filter; `from_date`; empty list when nothing is open), `book` (locks the branch row so two people can't both take the last seat; retrying the same booking returns the same id; refuses times that aren't open slots, full slots, other companies' branches/contacts), `cancel` (frees the seat at once). All times compared in UTC.
  - `tests/test_booking.py`: 50 tests: schedule → slots, weekly repeat, closing-time boundary (ends exactly at closing: in; crossing: out), holidays, past (a slot starting right now is too late), Friday closed, empty schedule, limit/window/from_date, overlapping rows, branch separation and filter, other company never shown; Dhaka (no daylight saving); London on the day clocks go back (right UTC, repeated hour uses the first, real 1-hour length), on the day clocks go forward (a skipped time has no slot, an hour that doesn't exist gives none); invalid/unknown company timezone; booking, full, retry, not-a-slot, holiday, other company, naive times; **two people racing for the last seat: exactly one gets it**; cancel frees the seat, twice refused, other company refused.
- Changed files:
  - `INSTRUCTION.md`: P2.4 renamed to appointments; P4.3 neutral tools (`book_appointment`), handoff reasons = core + pack, pack `[terms]` (D-020); new working rule **"Escape sequences in files (backslash rule)"**.
  - `PRD.md`: flow, F14, §9.4 tools table, Appendix A (`book_appointment`).
  - `packs/study_abroad/prompt.md`: `book_counselling` → `book_appointment`.
- Deleted files: none
- Decisions referenced: D-009, D-010, D-020
- Bugs found:
  1. **Real bug:** on the night clocks go back, Python treats the two 01:30s as equal when they share a timezone, so a booking for the second 01:30 (not a slot) could slip through as the first. Fixed by comparing every time in UTC; regression test added.
  2. **My tests:** the Friday test's week began on a Sunday whose slot had passed (5 days, not 6); the contact helper made a second web channel (one per company). Fixed.
  3. **Mutation check:** my clock-change test hid a "skipped hour kept" bug because the wrong slot merged with a real one; added the exact case (a schedule only inside the missing hour gives no slot). One mutation of mine was badly written (swapped parameters); rewritten properly and caught.
  4. **The backslash problem again** (\n turned into a real line break in my mutation script, the 5th time): owner asked for a permanent fix → rule added to INSTRUCTION.md and to Claude's memory; this entry follows it.
- Gate result (full logs saved):
  - G4: ruff check exit 0; format exit 0 (39 files); invisible-character scan of `app/` and `tests/`: clean
  - G1: 1195 passed
  - G2/G3: `app/booking.py` 96 stmts / 30 branches 100%; TOTAL 1125 / 462 **100%**
  - G6: reverse order: 1195 passed
  - G7: 1195 passed ×3 (3:09, 2:47, 2:40); no problems in logs; no file changed; 0 leftover databases
  - Mutation check (crash-safe, restored byte-identical): **18/18 caught** after the fixes above
  - G8 manual check: demo company (Banani 10-13 ×2 seats, Online 15-19 ×1, Friday closed, a holiday): Thursday 17:01 → only today's 18:00 left, Friday and the holiday absent, 29 slots in 7 days; booking hides the slot, retry gives the same id, cancel brings it back.
- Note: full test run is now ~3 min (DB-heavy booking tests); still well under the 5-minute limit.
- `# pragma: no cover` uses: none
- Owner sign-off: **signed off** 2026-09-24 ("g")

### C-025 Portion P2.5: Sensitive-data redaction
- Date: 2026-09-24
- Type: portion
- New files:
  - `app/redact.py`: `redact(text)` replaces card numbers (13-19 digits passing the Luhn check, written in one piece or grouped like a card: 4-4-4-4 or 4-6-5), NIDs (10/13/17 digits; with spaces only when every piece has 3+ digits) and passport-like numbers (1-2 letters + 7-8 digits, standing alone, any case) with `[card]`, `[nid]`, `[passport]`. Digits of any script count (Bangla included). Valid Bangladesh phone numbers are always kept (D-014), including a 13-digit `880...` phone that looks like an old NID, and phones next to other numbers. Money, dates, times, scores untouched. Redacting twice changes nothing more. No backslashes in the file (patterns use `[0-9]`), per the new backslash rule.
  - `tests/test_redact.py`: 75 cases: 10 card forms (incl. Amex grouping, 13 and 19 digits, Bangla digits), non-Luhn/too-short/too-long kept, card next to another number, numbers that happen to pass the card check but aren't written like a card (two money amounts side by side) kept; 6 NID forms, other lengths kept, "2026 2027 20" kept; 5 passport forms, 7 look-alikes kept; 7 phone forms kept, phones next to other numbers kept (incl. 17 and 13 digits together); 7 money forms and 6 ordinary messages unchanged; several items at once; passport followed by a number redacted once; 2 hypothesis properties (never raises + idempotent; a random Bangladesh phone anywhere in random text survives).
- Changed files: none
- Deleted files: none
- Decisions made here: the phone rule wins over the NID rule (a valid phone is never redacted); passports accept 7-8 digits and lower-case letters (the spec said 7; 8-digit e-passports exist); a 10-digit plain number (e.g. 100 crore written without commas) is treated as an NID; privacy first.
- Decisions referenced: D-014
- Bugs found:
  1. **Found while planning tests (mine):** a number and a phone separated by a space could join into an NID-length number and hide the phone. Fixed: runs containing a phone are checked piece by piece.
  2. **Mutation check found 5 test gaps:** my "odd grouping" test had 17 digits, not 16, so it never tested its claim; no test for money pairs that happen to pass the card check; none for a 17-digit phone+number; none for a 13-digit phone next to a number; none for a passport followed by a number (double redaction). All added. One redundant phone check in the card rule removed (a phone can't be written in card grouping).
- Gate result (full logs saved):
  - G4: ruff check exit 0; format exit 0 (41 files); invisible-character scan: clean
  - G1: 1270 passed
  - G2/G3: `app/redact.py` 62 stmts / 26 branches 100%; TOTAL 1187 / 488 **100%**
  - G6: reverse order: 1270 passed
  - G7: 1270 passed ×3 (2:44, 2:28, 2:34); no problems in logs; no file changed; 0 leftover databases
  - Mutation check (crash-safe, restored byte-identical): **16/16 caught**, plus 1 control mutation (no effect) correctly reported as missed, proving the harness can tell the difference
  - G8: none (pure function)
- `# pragma: no cover` uses: none
- Owner sign-off: **signed off** 2026-09-24 ("g")

### C-026 Portion P2.6: Abuse guards (Level 2 complete)
- Date: 2026-09-24
- Type: portion (D-018, D-019)
- New files:
  - `app/guard.py`: `check_input(text)` (before any AI call, free): pasted code (a code fence; 3+ code-looking lines: indented bodies, code starts like `def`/`import`/`#include`/`for(`, SQL clauses, lines ending in braces, or `;` lines with `( = [`; a one-liner with braces and 2+ semicolons, or a code start with a semicolon) → "code"; a base64/hex run of 200+ characters → "encoded"; jailbreak phrases in English, Banglish and Bangla, matched as whole words after folding (capitals, full-width letters, zero-width characters, line breaks, punctuation and spelled-out letters "I G N O R E" can't hide them) → "jailbreak". `check_reply(text, max_chars=2000)`: code → "code", over the channel limit → "too_long". No backslashes in the file.
  - `tests/test_guard.py`: 180 cases: 52 real English/Banglish and 40 real Bangla messages pass (incl. "act as a sponsor", "tell me the rules for dependants", "new instructions for UK visa", "pretend to be employed", "contact as a developer", "dev modern", "I-20 sponsor", form lines ending in ";", "Tuition = 12 lakh" lists, "For UK:" headings); 31 jailbreaks blocked; 3 phrases × 6 disguises; 10 code forms blocked, 2 lines not enough; encoded blob boundary; good replies (incl. price lists, headings, indented bullets) sent, code replies stopped, length limit; hypothesis: never raises.
- Changed files: `app/quick_answers.py`: the text folding moved into `fold_text` (shared with the guard) and now drops every invisible format character (zero-width spaces, word joiners), not only the two Bangla joiners; `normalize_trigger` uses it (all 131 quick-answer tests still pass).
- Deleted files: none
- Decisions referenced: D-018, D-019
- Bugs found (all mine, all fixed before sign-off):
  1. **Over-blocking found while writing the real-message list:** "tell me the rules", "new instructions", "pretend to be", "Name: Rahim;" form lines would have been blocked. Patterns narrowed.
  2. **Code detection missed Python and SQL** (only 2 of 5 lines counted); added indentation and SQL clauses. Then noticed that assignment/heading rules would block normal AI replies ("Total = £21,000", "For UK:"); dropped them, indentation carries Python.
  3. **The manual check caught 3 abuse attempts the tests missed:** "act as a senior python developer" (two words), "I G N O R E your rules" (spelled out), "for(int i=0;...){...}" (one brace pair). Fixed and added as tests.
  4. **Mutation check found 7 test gaps** over two rounds: phrase matching inside words ("contact as a developer", "dev modern"), exactly-3-line code, brace one-liner without a code start, braces with one semicolon, "I-20" read as "ai", three words before "developer". All added.
  5. An auto-formatted multi-line rule was only half-removed by my line filter (syntax error, caught by lint); fixed directly.
- Gate result (full logs saved):
  - G4: ruff check exit 0; format exit 0 (43 files); invisible-character scan: clean
  - G1: 1450 passed
  - G2/G3: `app/guard.py` 62 stmts / 26 branches 100%, `app/quick_answers.py` 176 / 78 100%; TOTAL 1250 / 514 **100%**
  - G6: reverse order: 1450 passed
  - G7: 1450 passed ×3 (2:21, 2:43, 2:44); no problems in logs; no file changed; 0 leftover databases
  - Mutation check (crash-safe, restored byte-identical): **25/25 caught**
  - G8 manual check: 20 real questions (English, Banglish, Bangla, phones, links, prices): 0 blocked; 20 abuse attempts (jailbreaks, disguised, Banglish/Bangla, Python/SQL/C, base64): 0 let through.
- Honest limit: phrase lists can't catch every rewording (e.g. homoglyph letters from other alphabets); the AI's core rules (D-018), the reply check and the eval set (P7.1) are the next layers.
- `# pragma: no cover` uses: none
- Owner sign-off: pending

### C-027 Fix: CI #5 failed on Linux and macOS (Cherokee letters in quick-answer triggers)
- Date: 2026-09-25
- Type: bug fix (found by CI, not locally)
- What failed: `test_normalized_triggers_satisfy_the_database_rule` on ubuntu and macos (1 failed, 1194 passed); Windows passed. Hypothesis input: the Cherokee letter A (U+13A0).
- Cause: Unicode's `casefold()` maps lower-case Cherokee **to upper-case** (a stability rule unique to Cherokee: all 172 affected characters are Cherokee, checked over every code point). The trigger was saved upper-case; PostgreSQL on Linux/macOS lower-cases Cherokee, so the database's "triggers are lower-case" rule rejected it. PostgreSQL on Windows doesn't lower-case Cherokee, so it passed locally.
- Fix: `fold_text` applies `lower()` after `casefold()` (`app/quick_answers.py`, one line). Checked over all of Unicode that casefold-then-lower gives stable output (0 exceptions).
- Tests: `tests/test_quick_answers.py`: the stability property now also asserts the result is lower-case (so this is caught on every OS, not only by a Linux database); new test for 3 Cherokee inputs. With the fix removed, 3 tests fail on Windows.
- Gate: G4 exit 0 (43 files), invisible-character scan clean; G1 1453 passed; G2/G3 TOTAL 1250 / 514 **100%**; G6 1453 passed; G7 1453 ×3; no problems in logs; no file changed; 0 leftover databases.
- Lesson → new rule in INSTRUCTION.md: a portion isn't finished until CI is green on all three OSes after the owner pushes (the databases on Linux/macOS behave differently from Windows).
- `# pragma: no cover` uses: none
- Owner sign-off: pending (after CI is green)

### Existing files at the start of the log
- `PRD.md` (v2.1): product requirements. Source of truth for *what* to build.
- `BUILD_PROMPT.md`: session prompt for Claude Code.

---

## Open items
- **O-001** Remove the `anyio.abc.BlockingPortal` warning ignore in `pyproject.toml` when a Starlette release stops using the deprecated alias (check at each dependency update).
- **O-002** Git and GitHub are handled by the owner (2026-09-23): the owner runs `git init`, commits and pushes to a private repo. Claude doesn't run git commands on this project unless asked. Before each push, the owner checks that `.env` and `.venv/` aren't staged.
- **O-003** (resolved 2026-09-23) Intermittent "1 error" in the test suite. Root cause: autovacuum race on `DROP DATABASE WITH (FORCE)` in the test fixture (C-008). Fixed with bounded retry + tests. **If any unexplained error appears again, P1.1 re-opens.**
- **O-005** Tenant `timezone` is only checked for non-empty in the database (a CHECK can't look up the timezone list). Validate it against `zoneinfo.available_timezones()` in the operator console when a tenant is created or edited (P6.3).
- **O-006** ~~Gate time~~ **Resolved (D-017, C-019):** full run 4-6.5 min → ~1:45 in parallel.
- **O-007** Encryption-key rotation (PRD §12.2): `encrypt`/`decrypt` use one `FERNET_KEY`. Add rotation (e.g. `MultiFernet` with old + new keys, then re-encrypt stored secrets) with its runbook in P7.2.
- **O-008** Before the first client signs: lawyer review of guardian consent for under-18 phone numbers (D-014) and of the DPA template.
- **O-013** `estimate_tokens` is a byte-based estimate (marked `ponytail:` in `app/knowledge.py`). Replace with the provider's token-count call when the AI client exists (P3).
- **O-009** Windows console encoding (cp1252) can't print Bangla when output is redirected. When structured logging is built (P7.2), write logs as UTF-8 explicitly (e.g. `sys.stdout.reconfigure(encoding="utf-8")` or `PYTHONUTF8=1` in the service settings) and test a Bangla log line.
- **O-010** `packs/study_abroad/prompt.md` and `knowledge_template.md` are now the source of truth; PRD Appendix A/B are copies. Change the pack files first and keep the PRD in step (or replace the appendices with pointers). The Docker image must include `packs/` (P7.2).
- **O-011** `phones.py` has a small calling-code table (13 countries). If the product serves many more countries, consider the `phonenumbers` library (Google's full rules) instead of growing the table by hand; that's a new dependency, so a decision.
- **O-012** Admin screens for quick answers (Level 6): list/add/edit/delete/switch off, history with one-click undo, permission checks (operator: all companies; company admin: own; counsellor: none), and a test that a company admin can't read or edit another company's answers.
- **O-004** The test role `chatbot_test` isn't a superuser (good), so tests can't use superuser-only features. If a later portion needs one (e.g. an extension), grant it explicitly and log a decision; never make the test role a superuser.
