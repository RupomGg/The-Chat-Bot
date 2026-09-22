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
- Owner action before P1.1: install PostgreSQL 16 (steps in INSTRUCTION.md §5.1).
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
- Status: **proposed**, needs owner confirmation
- Context: PRD Appendix E lists every environment variable for the finished product. Requiring all of them in P0.1 would force fake Meta/Telegram/Resend/Sentry values before any code uses them.
- Options: A) Require all Appendix E variables now. B) Each portion adds the variables its own code uses, with validation and tests.
- Decision (built this way in P0.1): **B.** P0.1 requires `ENV`, `DATABASE_URL`, `FERNET_KEY`, `SESSION_SECRET`, `PUBLIC_BASE_URL`. `SENTRY_DSN` moves to the observability portion; channel tokens move to P5.x.
- Why: no unused settings, so no fake values; every variable is validated by the code that needs it.
- Affects: `app/config.py`, `.env.example`, each later portion.

### D-006 API docs pages off in production
- Date: 2026-09-23
- Status: **proposed**, needs owner confirmation
- Context: FastAPI serves `/docs` and `/openapi.json` by default, which list every route to anyone.
- Decision (built this way in P0.1): on in `test`/`staging`, off in `production` (PRD §12.2 hardening).
- Affects: `app/main.py`.

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
- Owner sign-off: pending

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
- Owner sign-off: pending

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
- Owner sign-off: pending

### C-004 Expand .gitignore before the owner's first push
- Date: 2026-09-23
- Type: docs
- New files: none
- Changed files:
  - `.gitignore`: grouped with comments; added `*.pem`, `*.key`, `venv/`, `*.log`, `*.dump`, `*.sql.gz`, `.vscode/`, `.idea/`, `*.swp`, `Thumbs.db`, `desktop.ini`, `.DS_Store` · why: keep secrets, logs, database dumps and editor/OS files out of GitHub · depends: owner's git workflow (O-002).
- Deleted files: none
- Verification: in a scratch repo (not the project), 15 paths that must be ignored (`.env`, `.env.local`, `.env.production`, `.venv/`, caches, `*.log`, `*.pem`, `.vscode/`, `Thumbs.db`, `*.dump`, …) → all ignored; 8 that must be tracked (`.env.example`, `app/config.py`, tests, `pyproject.toml`, `migrations/001_init.sql`, docs, `.gitignore`) → all tracked.
- Tests: unchanged (no code touched).
- Owner sign-off: pending

### Existing files at the start of the log
- `PRD.md` (v2.1): product requirements. Source of truth for *what* to build.
- `BUILD_PROMPT.md`: session prompt for Claude Code.

---

## Open items
- **O-001** Remove the `anyio.abc.BlockingPortal` warning ignore in `pyproject.toml` when a Starlette release stops using the deprecated alias (check at each dependency update).
- **O-002** Git and GitHub are handled by the owner (2026-09-23): the owner runs `git init`, commits and pushes to a private repo. Claude doesn't run git commands on this project unless asked. Before each push, the owner checks that `.env` and `.venv/` aren't staged.
