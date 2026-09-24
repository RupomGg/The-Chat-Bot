# INSTRUCTION.md: How we build this project, portion by portion

This file is the build plan and the rulebook. `PRD.md` says **what** to build; this file says **in what order** and **when a portion counts as finished**. `DECISION.md` records **every** file created or changed and why.

Audience: you (product owner) and Claude (engineer). Start every Claude Code session with:

> Read `INSTRUCTION.md`, `DECISION.md` and the PRD sections listed for portion **P?.?**. Build only that portion, following the rules in INSTRUCTION.md. Stop at the gate.

---

## 1. The rules

### 1.1 One portion at a time
- A portion is small: typically 1–4 source files plus their tests. Each is listed in §4 with its files, PRD references and required corner cases.
- **Never start the next portion until the current one passes its gate (§2) and you have signed off.**
- Never "quickly" add something from a later portion. If a later need shows up, note it in DECISION.md under *Open items*.

### 1.2 Tests first, then code
For every portion:
1. Read the PRD sections listed for the portion.
2. Write the **corner-case list** from §4 into the test file as test names *before* writing implementation code. Add any extra corner cases found while reading.
3. Implement until all tests pass.
4. Run the **whole** suite, not just the new tests, so a new portion can't silently break an old one.
5. Run the gate (§2).
6. Log everything in DECISION.md (§3).
7. Show the gate output to the owner. Wait for sign-off.

### 1.3 Handling bugs
- A bug found at any time gets: (1) a failing test that reproduces it, (2) the fix, (3) the test passing, (4) a DECISION.md entry of type `fix` naming the root cause.
- **Fix the root cause in the shared function**, not a patch at one call site. Check every caller.
- A bug in an already-signed-off portion re-opens that portion: its gate must pass again.
- **Never** delete, skip (`@pytest.mark.skip`) or weaken a test to make the suite pass. If a test is wrong, say so, fix it, and log the reason.

### 1.4 What "sure there's no underlying bug" means
Coverage alone doesn't prove correctness. A 100%-covered function can still be wrong. So a portion is only done when **all** of these hold:
- Every corner case in its §4 list has a test, and each test asserts a *specific* outcome (not just "doesn't crash").
- Failure paths are tested as seriously as happy paths: bad input, missing data, network errors, duplicates, concurrency, time boundaries.
- The code has been re-read once, top to bottom, asking "what input breaks this?". Anything found becomes a test.
- The owner has seen the gate output.

---

## 2. The gate ("100/100")

A portion passes only when **every** line below is true. Claude pastes the real command output into the session. A summary like "all good" doesn't count.

| # | Check | Command | Pass condition |
|---|---|---|---|
| G1 | All tests pass | `python -m pytest -q` | 0 failed, 0 errors, 0 skipped, 0 xfail |
| G2 | Full coverage on the portion's code | `python -m coverage run -m pytest -q` then `python -m coverage report --fail-under=100 --include="<portion files>"` | 100% lines **and** branches (`branch = true` in config) |
| G3 | Whole-project coverage doesn't drop | `python -m coverage report --fail-under=100` | 100% across `app/` (from portion P0.1 on) |
| G4 | Lint + format | `python -m ruff check .` and `python -m ruff format --check .` | No findings |
| G5 | No warnings | `pyproject.toml` has `filterwarnings = ["error", ...]`, so every G1 run already fails on any warning. Check: the config still starts with `"error"`, and every `ignore:` line targets one exact third-party message with a comment + DECISION.md open item | No broad ignores; don't pass `-W error` on the command line (it overrides the narrow ignores) |
| G6 | Tests are order-independent | Normal run (G1), then reverse file order: `python -m pytest -q $(ls tests/test_*.py \| sort -r)` | Both pass |
| G7 | Tests are stable | Run G1 three times in a row | Same result every time (no flaky tests) |
| G8 | Manual check | The portion's "Manual check" line in §4 | Owner sees it work |
| G9 | Logged | DECISION.md entry for this portion | Lists every new/changed file, why, and the gate result |

**Save full output.** Every gate command writes its complete output to a file first; the summary shown to the owner is taken from those files. Never pipe a gate run straight into `tail`. A one-off error must be traceable afterwards (lesson from P1.1, O-003).

**Deliberate-bug checks (mutation checks) must be crash-safe.** Before breaking a file on purpose, copy it to a backup **outside the project**; restore from that backup in a `finally`; finish by confirming the file is byte-identical to the backup (SHA-256). At the start of any session after an interrupted check, verify the file against the backup before anything else (lesson from P1.2: an interrupted run left `001_init.sql` missing a rule until caught).

**Capture errors and exit codes, not just output.** Every gate command redirects both output streams to its log (`> log 2>&1`) and reports its **exit code**. A blank summary line is a failure until proven otherwise (lesson from C-014: after a crash, ruff panicked on a corrupted cache and printed nothing to stdout, which looked like "clean").

**Escape sequences in files (backslash rule).** The file-writing tools, and Python scripts pasted into the shell, can turn a written `\n`, `\t` or `\uXXXX` into the real character (a line break, a tab, an invisible joiner) instead of keeping the escape. It happened 5 times (P2.1b, P2.2 twice, P2.2 tests, P2.4 mutation script). So: (1) never put a backslash escape inside text that a script writes into another file; build it with `chr(92)` (e.g. `chr(92) + "n"`) or edit the file directly with the Edit tool; (2) invisible or special characters (joiners, accents, emoji used as data) are always written as escapes in source, never raw; (3) after writing any line that contains a backslash, show that exact line (`sed -n`/`grep -n`) and confirm the escape is still there, then run `ruff check` (catches broken strings) and the invisible-character scan (Unicode categories Cf/Cc outside `\n`, and stray combining marks) on every changed file. A file that fails this is not finished.

**After a crash or power loss:** before anything else, (1) scan project files for zero-filled or blank files, (2) verify files against the last saved SHA-256 fingerprints and mutation backups, (3) delete tool caches (`.ruff_cache`, `__pycache__`, `.pytest_cache`, `.hypothesis`, `.coverage`); they're rebuilt automatically, (4) confirm PostgreSQL is running and no test databases are left, (5) rerun the full gate.

**A single unexplained failure blocks the gate.** Rerunning until it's green is not a fix. Find the root cause (server logs, leftover state), fix it, add a test, log it.

`# pragma: no cover` is allowed only for code that truly can't run in tests (e.g. `if __name__ == "__main__":`), and each use must be listed in the DECISION.md entry with a reason.

---

## 3. How to log in DECISION.md

Every portion adds one entry (format in DECISION.md). Every file touched is listed:
- **New file:** path + one line on its job.
- **Changed file:** path + what changed + why + which other files depend on it (so nothing breaks unnoticed).
- **Deleted file:** path + why + what replaces it.

Decisions (choices between options) get their own `D-###` id and are referenced from portion entries.

---

## 4. The portions

Levels group portions. Finish a level before starting the next one. Every portion lists: **Goal · Files · PRD refs · Corner cases (must each be a test) · Manual check.**

### Level 0: Foundation

**P0.1 Project skeleton and tooling**
- Goal: an empty but correctly configured Python project that starts and answers `/healthz`.
- Files: `pyproject.toml` (deps pinned, ruff + coverage + pytest config), `app/__init__.py`, `app/config.py`, `app/main.py`, `tests/conftest.py`, `tests/test_config.py`, `tests/test_health.py`, `.gitignore`, `.env.example`, `README.md`.
- PRD refs: §8.1, §8.2, §12.2, Appendix E.
- Corner cases:
  - each required env var missing → startup fails with a message naming the variable (without printing any secret value);
  - `ENV` not in {`staging`, `production`, `test`} → fails;
  - `FERNET_KEY` not a valid Fernet key → fails at startup, not at first use;
  - `DATABASE_URL` malformed → fails with a clear message;
  - `PUBLIC_BASE_URL` without `https://` in production → fails;
  - config object is immutable after load;
  - `/healthz` returns 200 with `{"status":"ok"}` when healthy and never includes secrets;
  - `repr()`/logging of config masks secret fields.
- Manual check: `uvicorn app.main:app` runs; browser shows `/healthz` OK.

**P0.2 Continuous integration**
- Goal: every push runs the full gate automatically.
- Files: `.github/workflows/ci.yml`.
- PRD refs: §8.1 (CI/CD), §12.2.
- Corner cases: CI uses the same Python version as local; a Postgres service is available to tests; a failing test fails the job; a coverage drop fails the job; secrets are not required for the test job.
- Manual check: push a branch with a deliberately failing test → CI red; revert → green.

### Level 1: Data layer

**P1.1 Database connection and migration runner**
- Goal: numbered SQL migrations applied safely at startup.
- Files: `app/db.py`, `migrations/000_schema_version.sql`, `tests/test_db.py`.
- PRD refs: §8.1 (DB access, migrations), §12.1.
- Corner cases:
  - fresh DB → all migrations applied in numeric order;
  - re-run → nothing re-applied (idempotent);
  - a migration with an SQL error → that migration rolled back completely, earlier ones kept, startup fails loudly;
  - an already-applied migration file edited afterwards → checksum mismatch → startup refuses;
  - two app instances starting at once → migrations applied exactly once (advisory lock);
  - gap or duplicate in migration numbers → refused;
  - DB unreachable → clear error with retry/backoff, bounded total wait;
  - pool exhausted → request waits up to a timeout then fails cleanly.
- Manual check: start the app twice in parallel against an empty DB; `schema_version` shows each migration once.

**P1.2 Core schema**
- Goal: all tables from PRD §10 with constraints that make invalid data impossible.
- Files: `migrations/001_init.sql`, `tests/test_schema.py`.
- PRD refs: §10.
- Corner cases:
  - every `CHECK` rejects out-of-range values (conversation state, message role, channel type, booking status);
  - every `UNIQUE` rejects duplicates (`channels(type, external_id)`, `contacts(channel_id, external_user_id)`, `messages(conversation_id, external_id)`, `users.email` case-insensitively);
  - foreign keys reject orphans; deleting a tenant with data is refused (no silent cascade);
  - `messages.external_id` NULL allowed many times but non-NULL unique per conversation;
  - timestamps are `timestamptz` and default to now;
  - money/cost uses `numeric`, never float.
- Manual check: `\d+` of each table matches PRD §10.

**P1.3 Security helpers**
- Goal: encryption, password hashing, signatures, CSRF, all in one small module.
- Files: `app/security.py`, `tests/test_security.py`.
- PRD refs: §12.2.
- Corner cases:
  - Fernet round-trip; wrong key → specific error; tampered ciphertext → error; empty string round-trips;
  - scrypt: correct password verifies; wrong one fails; comparison is constant-time (`hmac.compare_digest`); two hashes of the same password differ (salt); unicode/Bangla passwords work; password < 12 chars rejected;
  - Meta signature: valid → true; missing header, wrong `sha256=` prefix, wrong length, non-hex, body changed by 1 byte, wrong app secret → false (never an exception to the caller);
  - Telegram secret header: exact match only, constant-time;
  - CSRF token: valid for its session only; expired/other-session/missing → rejected.
- Manual check: none beyond the gate (pure functions).

**P1.4 Migration 003: contact details, tenant settings, quick answers + history** (added 2026-09-23, D-015): `contacts.email`, `tenants.settings`, `quick_answers`, `quick_answer_history` with database-written history and one-trigger-per-company rule (incl. two admins saving at once). Done: C-017.

### Level 2: Core domain logic (pure code, no network)

Everything industry-specific comes from the tenant's **industry pack** (PRD §0, D-012). Portions in Levels 2–7 must never hard-code study-abroad rules in the core; they read them from the pack. The study_abroad pack is the only one built for now.

**P2.0 Industry pack loader**
- Goal: load and validate a pack folder so a broken pack can never reach a tenant.
- Files: `app/packs.py`, `packs/study_abroad/pack.toml` (profile fields, scoring rules, stage labels, handoff rules), `packs/study_abroad/prompt.md`, `packs/study_abroad/knowledge_template.md`, `tests/test_packs.py`, `tests/fixtures/packs/` (small valid and broken packs). Uses stdlib `tomllib`, no new dependency.
- PRD refs: §0, §5.2, §5.3, Appendix A–C.
- Corner cases: valid pack loads; missing folder or file → clear error naming it; unknown key (typo) → error; profile field with unknown type → error; scoring rule referring to a field that doesn't exist → error; stage labels must cover exactly the 7 generic stages; prompt template placeholders all known (no stray `{{x}}`); pack name must match the folder and the `tenants.industry` format; loading the same pack twice returns equal results; Bangla text in labels loads correctly; a second tiny fixture pack (e.g. `pet_care_sample`) loads to prove nothing is study-abroad-only.
- Manual check: print the loaded study_abroad pack summary.


**P2.1 Phone normalization**
- Files: `app/phones.py`, `tests/test_phones.py`. PRD refs: §5.2, §19.1.
- Corner cases: `01712345678`, `+8801712345678`, `8801712345678`, `008801712345678` → same E.164; spaces, dashes, dots and brackets stripped; **Bangla digits** `০১৭১২৩৪৫৬৭৮` converted; BD prefix `01[3-9]` enforced (`012…` rejected); wrong length rejected; landline-looking numbers rejected for BD; non-BD tenant (e.g. `+977` Nepal) validates by country length rules only; empty/None/emoji/letters rejected; a number embedded in a sentence is **not** extracted by this function (the model passes the number only); property tests (hypothesis): any accepted number re-normalizes to itself, and random unicode never raises (only returns "invalid").
- Manual check: none.

**P2.1b Contact-detail checks** (added 2026-09-23, D-015)
- Files: `app/contact_details.py`, `tests/test_contact_details.py`.
- Functions, each returning a clean value or None (never raising on user input): `normalize_email` (trim, lower-case the domain, international domain names via IDNA, ≤ 254, one `@`, dotted domain); `normalize_name` (trim, collapse spaces, 1-100 characters, any script incl. Bangla, no control characters, not emoji-only); `normalize_country` (ISO 3166 two-letter code from code or common name, e.g. "Bangladesh"/"bd" → "BD"); `normalize_year_month` ("2027-01", "Jan 2027", "01/2027", "জানুয়ারি ২০২৭" → "2027-01"); `valid_timezone` (IANA names via `zoneinfo`); `normalize_https_url` (https only, real host, blocks `javascript:` and credentials in URLs).
- Corner cases: each function's accepted formats, boundaries (254/100 characters, month 1-12, years), Bangla digits and month names, junk (None, non-strings, emoji, control characters, very long input); hypothesis properties (never raises; accepted values re-normalize to themselves).
- Manual check: none (pure functions).

**P2.2 Quick answers from the database** (was: from the knowledge file; changed by D-015)
- Files: `app/quick_answers.py`, `app/knowledge.py`, `tests/test_quick_answers.py`, `tests/test_knowledge.py`. PRD refs: §6.8 (F45-F49), §9.3, D-015.
- `normalize_trigger(text)`: the one normalization used when saving triggers **and** when matching student text (lower-case, trim, collapse spaces, strip punctuation incl. `?`, `।`, emoji; Bangla preserved), so they always agree. Satisfies the database's trigger rules.
- `find_quick_answer(conn, tenant_id, *, payload=None, text=None, language)`: button payload → exact code; typed text → exact normalized trigger (no fuzzy matching); only `active` rows; only this tenant's rows; answer in the student's language, else English, else any available; returns follow-up buttons and action.
- `save_quick_answer(...)`, `delete_quick_answer(...)`, `undo_change(history_id)`: validate and normalize before the database sees it; set `app.user_id` in the same transaction so history records who; undo restores the `before` of a history row (re-creating a deleted answer or reverting an edit); friendly errors for duplicate code or trigger clashes.
- `app/knowledge.py`: business-info text for the AI prompt (versions, token count, byte-identical rendering, no stray `{{x}}`).
- Corner cases: payload vs typed text; inactive answers ignored; another tenant's answer never returned; language fallback order; answer-less action rows; trigger normalization property tests (idempotent, never raises, Bangla kept); saving triggers that normalize to the same text → clash reported; undo of create/update/delete; undo twice; undo of a history row from another tenant refused; concurrent saves (database rule already tested in P1.4).
- Manual check: create, edit, delete and undo a quick answer for the demo tenant and print the history.

**P2.3 Lead scoring** (engine in core; the rules below are the study_abroad pack's, read from `pack.toml`)
- Files: `app/scoring.py`, `tests/test_scoring.py`. PRD refs: §5.3.
- Corner cases: each rule on its own; **boundaries** (intake exactly 9 months, 9 months + 1 day, exactly 18 months); intake in the past; intake missing; MOI counts as English; "test booked" counts; funding scholarship-only blocks Hot; country not served blocks Hot; no phone → never above Cold; each flag (refusal, gap ≥ 5 exactly and 4, scholarship-only); "today" injected (never read the real clock inside the function); month arithmetic across year end (Nov → Aug next year).
- Manual check: none.

**P2.4 Appointment slots and bookings** (generic, D-020: a counselling session, a vet visit or a dental check-up; the pack names it)
- Files: `app/booking.py`, `tests/test_booking.py`. PRD refs: §6.2 (F14–F15).
- Corner cases: weekly schedule → slots; slot ending exactly at closing time included, one crossing it excluded; holidays excluded; past slots excluded (now = injected); capacity respected; **two bookings racing for the last seat → exactly one succeeds** (DB transaction + row lock); cancelled booking frees capacity; overlapping schedule rows don't duplicate slots; a timezone with daylight saving (e.g. `Europe/London`) on the change date (for international tenants); Asia/Dhaka (no DST); Friday closed; empty schedule → "no slots" (not an error); request for 5 slots when only 2 exist returns 2.
- Manual check: print next week's slots for the demo tenant.

**P2.5 Sensitive-data redaction**
- Files: `app/redact.py`, `tests/test_redact.py`. PRD refs: §9.5.
- Corner cases: valid card numbers (Luhn-checked; with spaces/dashes) redacted; 16-digit non-Luhn strings not redacted; NID lengths 10/13/17 redacted; **11-digit BD phone numbers NOT redacted**; money amounts ("15,00,000 taka", "1500000") not redacted; passport-like `[A-Z]{1,2}\d{7}` redacted; Bangla digits handled; text with several items redacts all; redaction is idempotent (running twice gives the same text); property tests (hypothesis): random text never raises, and valid BD phone numbers inserted anywhere in random text always survive unredacted.
- Manual check: none.

**P2.6 Abuse guards: no one uses the bot as a free general AI** (added 2026-09-24, D-018, D-019)
- Files: `app/guard.py`, `tests/test_guard.py`. Pure functions, no network. PRD refs: §9.5.
- `check_input(text) -> None | reason`: runs **before** any model call and costs nothing. Blocks: pasted code (a ``` block, or 3+ lines that look like code: `def `, `function`, `class `, `#include`, `import `, `SELECT … FROM`, `public static`, `console.log`, lines ending in `{`, `}` or `;`); a base64/hex blob ≥ 200 characters; known jailbreak phrases in English, Banglish and Bangla ("ignore (all|previous|your) instructions/rules", "system prompt", "developer mode", "DAN", "jailbreak", "you are now", "pretend (you are|to be)", "act as a", "roleplay", "repeat the text above", "niyom gula bhule jao", "নির্দেশনা ভুলে যাও"). A block → fixed one-line redirect + quick-answer buttons, counts toward the off-topic streak (P4.4).
- `check_reply(text) -> None | reason`: runs on the model's reply **before sending**; blocks code (same rules) and replies longer than the channel limit; a block → redirect instead + `off_topic_blocked` event.
- Corner cases: **no false blocks on real customer messages**: fees with `;`, "IELTS 6.5; gap 2 years", addresses, phone numbers, URLs, emoji, Bangla and Banglish questions, "can a guardian act as sponsor?", "what is the process to apply?" (tested with ≥ 40 real-style messages per pack language); case-insensitive; zero-width characters, full-width letters and extra spaces can't hide a phrase (normalize like `normalize_trigger`); a phrase split across lines still caught; hypothesis: never raises on any text.
- Manual check: run 20 real questions and 20 abuse attempts through both functions and read the results.

### Level 3: Background jobs

**P3.1 Job queue and worker**
- Files: `app/jobs.py`, `app/worker.py`, `tests/test_jobs.py`. PRD refs: §8, §12.1.
- Corner cases: enqueue + process once; `run_at` in the future not picked early; failure → retry with exponential backoff; max attempts → `dead` + alert hook called; **two workers never process the same job** (SKIP LOCKED, tested with two concurrent claimers); worker killed mid-job → lock expires → job picked up again (stale-lock recovery); handler must be idempotent → duplicate delivery doesn't double side effects (tested with a counter); unknown job kind → dead immediately with a clear error; payload not JSON-serializable → rejected at enqueue; graceful shutdown finishes the current job; queue depth + oldest-job age exposed for `/healthz`.
- Manual check: run the worker, enqueue a job that fails twice then succeeds; watch the retries in logs.

### Level 4: AI engine

**P4.1 Prompt assembly**
- Files: `app/prompts.py`, `prompts/system.md`, `tests/test_prompts.py`. PRD refs: §9.2, Appendix A.
- Corner cases: system block byte-identical for the same tenant and knowledge version; changes when knowledge changes; context block contains time in the tenant's timezone, channel, profile JSON with sorted keys; history limited to the last 12 messages (the profile JSON carries earlier facts, so older turns aren't needed; fewer tokens, and multi-turn jailbreaks lose their build-up) (D-019); conversation split after 72 h idle; `staff` messages rendered so the model knows a human spoke; quick-answer messages included; empty history works; a very long student message is capped at 1,000 chars *before* the prompt (D-019); tool results are compact JSON (no spaces, sorted keys); system block = pack prompt + knowledge + core rules, then one cache breakpoint; nothing that changes per turn (time, profile) before it.
- Manual check: print the assembled request for the demo tenant.

**P4.2 LLM call (Claude)**
- Files: `app/llm.py`, `tests/test_llm.py`. PRD refs: §9.1, §9.2.
- Corner cases (with a fake client, no network): stop reason `end_turn`, `tool_use`, `max_tokens` (→ fallback + event), `refusal` (→ fallback + handoff); API errors 400/401/404 (→ fallback + operator alert, no retry), 429/500/529/timeout/connection error (SDK retries, then fallback); response with no text block; cost computed from usage including cache-read and cache-write tokens with the right per-model prices; unknown model id → error at config time, not at call time; model id prefix `gemini-` routes to the Gemini function (stub raises "not implemented" until P7.1).
- **Token settings (D-019):** `max_tokens` 500 for customer replies (a customer answer never needs more; a jailbroken reply is cut short and useless as a general AI); on `max_tokens` stop the reply goes through `check_reply`, and if it isn't a complete answer → fallback + event; `temperature` 0.2 on Haiku 4.5 for consistent, grounded answers, **omitted** on models that reject it (Sonnet 5 returns a 400); cache TTL 5 min by default, 1 h only for tenants with steady traffic (1 h cache writes cost 2×, reads 0.1×); on Haiku 4.5 nothing is cached below 4,096 tokens of fixed prompt, which is fine (small prompts are cheap) but the dashboard must show it; token counts from `count_tokens`, replacing the estimate (O-013). Tests: `max_tokens`/`temperature` present or absent per model; the request body never contains per-turn values before the cache breakpoint.
- One **real** smoke test, marked `@pytest.mark.live`, run on demand with a real key (not in CI): a two-turn chat shows `cache_read_input_tokens > 0` on turn 2.
- Manual check: run the live smoke test once; record tokens and cost in DECISION.md.

**P4.3 Tools**
- Files: `app/tools.py`, `tests/test_tools.py`, `app/packs.py` (extended). PRD refs: §9.4, §5.2.
- **Industry-neutral tools (D-020):** `update_profile`, `list_slots`, `book_appointment`, `register_event`, `log_unanswered`, `off_topic`, `request_handoff`. `request_handoff.reason` = core reasons (`asked_for_human`, `complaint`, `unanswered`, `integrity`) + the pack's own `handoff_reasons` (study_abroad: `visa_case`, `fee_dispute`). The pack loader gains `handoff_reasons` (identifiers, no clash with core reasons) and `[terms]` (`appointment`, `staff`: a label per language, same rules as stage labels); tests with both packs.
- Corner cases: every tool schema is strict (`additionalProperties: false`); server-side validation re-runs even though the API validates; invalid phone → tool result tells the model what's wrong (no exception); `update_profile` with an empty object → no-op; unknown field → rejected; under-18 → `adult = false` recorded and the phone **is** stored (D-014); `book_counselling` on a full slot → "slot taken" result with alternatives; `book_counselling` on a past slot → rejected; `request_handoff` twice → one handoff; unknown tool name → error result; tool input that isn't valid JSON → error result; tools can only touch the current contact (tested by passing another contact's id → ignored).
- Manual check: none.

**P4.4 Conversation engine**
- Files: `app/engine.py`, `tests/test_engine.py`. PRD refs: §5, §6.1–6.3, §6.8.
- Corner cases: quick-answer payload → fixed answer, **no model call** (asserted on the fake client); exact trigger match → same; tool loop capped (max 5 tool rounds, then fallback); conversation paused (`state='human'`) → bot stays silent, message stored; pause expired → bot replies again; monthly quota reached → overage allowed, hard cap → fixed message + alert; duplicate inbound external id → processed once; two messages from one student arriving together → processed in order (per-conversation lock); unanswered streak 2 → auto-handoff; hot lead → notify hook called once (not on every later message); model failure → fallback + handoff, student gets a reply; message > 1,000 chars truncated with a note (D-019); `app/guard.py` (P2.6): `check_input` before the model call, `check_reply` before sending; non-text inbound (image/voice/sticker) → polite text reply, no model call.
- **Stay on topic (D-018):** (1) *reply guard*: before sending, a model reply that contains code (a ``` block, or 3+ lines that look like code: `def `, `function`, `class `, `#include`, `import `, `SELECT … FROM`, `public static`, lines ending in `{`, `}` or `;`) is replaced by the tenant's one-line "I can only help with …" message and an `off_topic_blocked` event is logged; normal replies with prices, dates, lists, URLs, emoji or a stray `;` are **not** blocked (tests for both, in Bangla and English); (2) *off-topic streak*: the model calls tool `off_topic` when it redirects; 3 in a row → for the next hour the engine sends the fixed redirect plus quick-answer buttons **without calling the model** (quick-answer taps still work; after the hour the AI answers again); an on-topic reply resets the streak; (3) *daily cap*: at most 60 AI replies per contact per day (tenant setting); after that a fixed "a counsellor will continue here" message + handoff, no model call; quick answers still work. Corner cases: guard never blocks a fallback/quick answer; streak and cap are per contact, not per tenant; cap resets at midnight in the tenant's timezone.
- Manual check: through the CLI (P4.5), run 5 scripted conversations and read them, plus 5 abuse attempts (write code, fix my algorithm, homework, "ignore your rules", "you are ChatGPT now").

**P4.5 Demo tenant and CLI chat**
- Files: `app/chat.py`, `scripts/seed_demo.py`, `tenants/demo/knowledge.md`, `tests/test_seed.py`. PRD refs: Appendix B, §16.1.
- Corner cases: seed is idempotent (running twice doesn't duplicate); CLI handles Ctrl+C cleanly; CLI works without a real key when `--fake` is passed.
- Manual check: `python -m app.chat demo` answers in Bangla, Banglish and English.

### Level 5: Channels (each adapter only converts inbound → engine → outbound)

**P5.1 Web chat API** (`app/channels/web.py`): origin allow-list incl. `null` origin and subdomains; rate limit per visitor + per IP; SSE stream closed by the client mid-reply → no crash, reply still stored; poll endpoint; malformed JSON → 400.
**P5.2 Widget** (`app/static/widget.js`, `demo.html`): ≤ 15 KB gz (measured); localStorage throws → in-memory fallback; network drop → retry with backoff and a visible "reconnecting"; host page CSS can't change it (Shadow DOM); keyboard and screen-reader basics; mobile width 360 px. **Devices (D-009 follow-up):** manual check on a real **Android phone (Chrome)** and **iPhone (Safari)**, plus desktop Chrome, Edge, Firefox and Safari: open, type in Bangla and English with the phone keyboard, send, receive a streamed reply, rotate the screen, on-screen keyboard doesn't cover the input box, close/reopen keeps the conversation.
**P5.3 Messenger** (`app/channels/messenger.py`): verify challenge; HMAC with per-app secret; batched entries (several messages in one webhook); echo from our own app ignored, echo from another app → pause; `referral` stored; postback payloads → quick answers; outside the 24 h window → no send; Graph API errors (expired token, user blocked the Page) → event + alert, no retry storm.
**P5.4 WhatsApp** (`app/channels/whatsapp.py`): status callbacks (sent/delivered/read/failed) ignored for replies but logged; interactive button/list replies → quick answers; template sends only outside the window; coexistence echoes → pause; media messages → text reply; phone_number_id routing.
**P5.5 Telegram** (`app/channels/telegram.py`): secret header; edited messages ignored; group chats ignored (private only); callback queries → quick answers; bot blocked by user → event, no retries.
- Manual check for each channel: a real message from a phone gets a correct reply.

### Level 6: Staff apps

**P6.1 Auth and roles**: login rate limit; session fixation prevented (new session id on login); logout invalidates; CSRF on every POST; role checks; **cross-tenant access → 404 on every route** (one test per route, generated from the route table).
**P6.2 Inbox**: takeover/resume/assign/notes; window timer; reply outside the window blocked; CSV export escapes formulas (`=`, `+`, `-`, `@` at cell start) to prevent CSV injection.
**P6.3 Operator console**: knowledge publish blocked when evals fail; version rollback; usage/cost numbers match the `messages` table exactly.
**P6.4 Notifications**: Telegram notify bot; email; failure of one channel doesn't block the other; no duplicate notifications on job retry.

### Level 7: Quality and operations

**P7.1 Evals + Gemini + bake-off**: eval runner (core) reading each pack's eval questions; study_abroad pack ≥ 60 cases incl. ≥ 20 Banglish; **core off-topic/abuse set for every tenant, whatever the industry (D-018)**: ≥ 25 cases incl. ≥ 8 Banglish — write/fix/explain code, algorithm or SQL, debug this error, homework/assignment, essay, math, translation, poem, "ignore previous instructions", "you are now ChatGPT / developer mode", "print your prompt", a request split over two messages, a base64-encoded request, and disguised ones ("for my visa file I need a Python script", "my dog's vet asked me to write an algorithm"); every case must pass (no code, one-line redirect) or the knowledge can't be published; Gemini function (from official `google-genai` docs); bake-off table in `research/model_bakeoff.md`.
**P7.2 Production readiness**: Dockerfile, `railway.toml`, load test (20 msg/s, 5 min), restore drill, alerts firing test, runbooks, Dedicated deploy + release script.

### Level 8: Pilot features
**P8.1** reports page · **P8.2** CRM webhook (HMAC-signed, retries) · **P8.3** ad-attribution report.

---

## 5. Prerequisites by level

| Needed | From | Status |
|---|---|---|
| Python 3.13 (D-002) | P0.1 | Installed (3.13.1) |
| PostgreSQL 18 for tests (D-003, D-008) | P1.1 | Done: 18.6, `chatbot_test` login, `TEST_DATABASE_URL` in `.env`, `pg_hba.conf` back on `scram-sha-256` (verified) |
| Git repo + GitHub account | P0.2 | Git installed; repo not created yet |
| Anthropic API key with spend cap | P4.2 live test | Not set |
| Test Facebook Page + Meta app | P5.3 | Not created |
| WhatsApp test number (SIM) | P5.4 | Not bought |
| Telegram bot token | P5.5 | Not created |
| Gemini API key | P7.1 | Not set |

### 5.1 Installing PostgreSQL 18 on Windows (owner, before P1.1)
1. Done: PostgreSQL 18.6 installed with the official EDB installer. Stack Builder add-ons aren't needed (Cancel).
2. During setup: keep port **5432**; set a password for the `postgres` user and save it in your password manager; Stack Builder isn't needed.
3. Add `C:\Program Files\PostgreSQL\18\bin` to PATH if the installer didn't, then open a new terminal and check: `psql --version` shows 18.x.
4. Create a test login (in `psql -U postgres`): `CREATE ROLE chatbot_test LOGIN CREATEDB PASSWORD '<choose one>';`
5. Put `TEST_DATABASE_URL=postgresql://chatbot_test:<password>@localhost:5432/postgres` in your local `.env` (never committed). Tests create and drop their own database with that role.

---

## 6. Commands (once P0.1 exists)

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m coverage run -m pytest -q && python -m coverage report --fail-under=100
python -m ruff check . && python -m ruff format --check .
uvicorn app.main:app --reload
```
