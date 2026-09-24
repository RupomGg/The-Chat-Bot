"""Quick answers (PRD §6.8, D-015): fixed replies to button taps and common typed questions,
with no AI call. Each company edits its own; the database records every change
(migration 003), so any change can be undone.
"""

import re
import unicodedata
from dataclasses import dataclass

from psycopg import errors
from psycopg.types.json import Jsonb

CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,39}$")  # same rule as the database
LANGUAGE = re.compile(r"^[a-z]{2}$")
ACTIONS = frozenset({"start_booking"})
MAX_TRIGGER = 100
MAX_TRIGGERS = 50
MAX_ANSWER = 2000  # Messenger's text limit, the smallest of our channels
MAX_BUTTONS = 3  # WhatsApp reply buttons, the smallest of our channels
TENANT_LOCK = 733  # the same per-tenant lock the database's trigger rule takes


class QuickAnswerError(ValueError):
    """A save, delete or undo was refused; the message says why, in words an admin can act on."""


@dataclass(frozen=True)
class QuickAnswer:
    id: int
    code: str
    text: str | None  # None: an action-only quick answer
    language: str | None  # language of `text`
    buttons: tuple[str, ...]
    action: str | None


# ---------- matching ----------


def fold_text(text: str) -> str:
    """Text reduced to what a reader sees: lower-case, full-width letters made normal,
    letters/marks/digits of any script kept, punctuation and emoji become one space,
    invisible format characters (zero-width spaces, joiners) dropped. Shared with the
    abuse guard (P2.6), so hidden characters can't split a word there either."""
    # casefold() turns lower-case Cherokee into upper-case (a Unicode rule), and databases on
    # Linux/macOS then see an upper-case letter; lower() afterwards fixes the only such script.
    text = unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", text).casefold().lower())
    kept = "".join(
        ""
        if unicodedata.category(ch) == "Cf"
        else ch
        if unicodedata.category(ch)[0] in "LMN"
        else " "
        for ch in text
    )
    return unicodedata.normalize("NFKC", " ".join(kept.split()))


def normalize_trigger(text) -> str | None:
    """The one normalization for saved triggers and for student text, so they always agree.

    'Fees??' → 'fees'; 'Office  kothay?' → 'office kothay'; 'ঠিকানা।' → 'ঠিকানা'.
    None when nothing is left or it's longer than any trigger can be.
    """
    if not isinstance(text, str) or len(text) > 10 * MAX_TRIGGER:
        return None
    result = fold_text(text)
    return result if result and len(result) <= MAX_TRIGGER else None


FIND_BY_CODE = """
SELECT id, code, answers, buttons, action FROM quick_answers
WHERE tenant_id = %s AND active AND code = %s
"""
FIND_BY_TRIGGER = """
SELECT id, code, answers, buttons, action FROM quick_answers
WHERE tenant_id = %s AND active AND %s = ANY (triggers)
"""


def find_quick_answer(conn, tenant_id, *, payload=None, text=None, language="en"):
    """This tenant's active quick answer for a button payload (exact code) or typed text
    (exact normalized trigger, no fuzzy matching). None: no match, so the AI answers.

    The answer is in the student's language, else English, else any language it has.
    """
    if (payload is None) == (text is None):
        raise TypeError("pass exactly one of payload or text")
    if payload is not None:
        if not isinstance(payload, str) or not CODE.match(payload):
            return None  # payloads come from outside: junk just doesn't match
        row = conn.execute(FIND_BY_CODE, (tenant_id, payload)).fetchone()
    else:
        trigger = normalize_trigger(text)
        if trigger is None:
            return None
        row = conn.execute(FIND_BY_TRIGGER, (tenant_id, trigger)).fetchone()
    if row is None:
        return None
    id_, code, answers, buttons, action = row
    if not isinstance(language, str):
        language = "en"
    chosen = next((lang for lang in (language, "en", *sorted(answers)) if lang in answers), None)
    return QuickAnswer(id_, code, answers.get(chosen), chosen, tuple(buttons), action)


# ---------- editing ----------


def _as_user(conn, user_id) -> None:
    """Who is making this change, for the history the database writes (NULL = system)."""
    if user_id is not None and (not isinstance(user_id, int) or isinstance(user_id, bool)):
        raise TypeError("user_id must be an int or None")
    value = "" if user_id is None else str(user_id)
    conn.execute("SELECT set_config('app.user_id', %s, true)", (value,))


def _clean_code(code, problems) -> str:
    clean = code.strip().upper() if isinstance(code, str) else ""
    if not CODE.match(clean):
        problems.append(
            f"code {code!r}: use 2-40 capital letters, digits or _, starting with a letter"
        )
    return clean


def _clean_triggers(triggers, problems) -> list[str]:
    if isinstance(triggers, str) or not isinstance(triggers, list | tuple):
        problems.append("triggers must be a list of phrases")
        return []
    if len(triggers) > MAX_TRIGGERS:
        problems.append(f"at most {MAX_TRIGGERS} triggers")
    seen: dict[str, str] = {}
    for raw in triggers:
        clean = normalize_trigger(raw)
        if clean is None:
            problems.append(
                f"trigger {raw!r}: needs letters or numbers, at most {MAX_TRIGGER} characters"
            )
        elif clean in seen:
            problems.append(f"triggers {seen[clean]!r} and {raw!r} are the same phrase ({clean!r})")
        else:
            seen[clean] = raw
    return list(seen)


def _clean_answers(answers, problems) -> dict[str, str]:
    if not isinstance(answers, dict):
        problems.append("answers must map a language code to text, e.g. {'en': '...'}")
        return {}
    clean = {}
    for lang, text in answers.items():
        if not isinstance(lang, str) or not LANGUAGE.match(lang):
            problems.append(f"answer language {lang!r}: use a 2-letter code such as 'en' or 'bn'")
            continue
        if not isinstance(text, str):
            problems.append(f"answer {lang}: must be text")
            continue
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            problems.append(f"answer {lang}: empty")
        elif len(text) > MAX_ANSWER:
            problems.append(f"answer {lang}: at most {MAX_ANSWER} characters")
        elif any(unicodedata.category(ch) == "Cc" and ch not in "\n\t" for ch in text):
            problems.append(f"answer {lang}: contains control characters")
        else:
            clean[lang] = text
    return clean


def _clean_buttons(buttons, problems) -> list[str]:
    if isinstance(buttons, str) or not isinstance(buttons, list | tuple):
        problems.append("buttons must be a list of quick-answer codes")
        return []
    if len(buttons) > MAX_BUTTONS:
        problems.append(f"at most {MAX_BUTTONS} buttons (WhatsApp shows no more)")
    clean = []
    for raw in buttons:
        code = raw.strip().upper() if isinstance(raw, str) else ""
        if not CODE.match(code):
            problems.append(f"button {raw!r}: not a valid quick-answer code")
        elif code in clean:
            problems.append(f"button {code} is listed twice")
        else:
            clean.append(code)
    return clean


def _friendly(error: errors.UniqueViolation, code: str) -> QuickAnswerError:
    if error.diag.constraint_name == "quick_answers_tenant_id_code_key":
        return QuickAnswerError(f"code {code} already exists for this company")
    return QuickAnswerError(error.diag.message_primary)  # trigger clash, worded by migration 003


INSERT = """
INSERT INTO quick_answers (tenant_id, code, triggers, answers, buttons, action, active)
VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
"""
UPDATE = """
UPDATE quick_answers
SET code = %s, triggers = %s, answers = %s, buttons = %s, action = %s, active = %s
WHERE tenant_id = %s AND id = %s RETURNING id
"""


def save_quick_answer(
    conn,
    tenant_id,
    *,
    code,
    triggers=(),
    answers=None,
    buttons=(),
    action=None,
    active=True,
    user_id=None,
    quick_answer_id=None,
) -> int:
    """Create (quick_answer_id=None) or replace one of this tenant's quick answers.
    Live immediately. Returns its id. Raises QuickAnswerError listing every problem."""
    problems: list[str] = []
    code = _clean_code(code, problems)
    clean_triggers = _clean_triggers(triggers, problems)
    clean_answers = _clean_answers({} if answers is None else answers, problems)
    clean_buttons = _clean_buttons(buttons, problems)
    if action is not None and action not in ACTIONS:
        problems.append(f"action {action!r}: must be one of {sorted(ACTIONS)} or none")
    if not isinstance(active, bool):
        problems.append("active must be true or false")
    if not problems and not clean_answers and action is None:
        problems.append("needs an answer in at least one language, or an action")
    if problems:
        raise QuickAnswerError("; ".join(problems))
    with conn.transaction():
        _as_user(conn, user_id)
        existing = {
            c
            for (c,) in conn.execute(
                "SELECT code FROM quick_answers WHERE tenant_id = %s AND code = ANY (%s)",
                (tenant_id, clean_buttons),
            )
        }
        missing = [b for b in clean_buttons if b not in existing and b != code]
        if missing:
            raise QuickAnswerError(f"button {', '.join(missing)}: no such quick answer")
        values = (code, clean_triggers, Jsonb(clean_answers), clean_buttons, action, active)
        try:
            if quick_answer_id is None:
                row = conn.execute(INSERT, (tenant_id, *values)).fetchone()
            else:
                row = conn.execute(UPDATE, (*values, tenant_id, quick_answer_id)).fetchone()
        except errors.UniqueViolation as error:
            raise _friendly(error, code) from None
        if row is None:
            raise QuickAnswerError("quick answer not found")
        return row[0]


def delete_quick_answer(conn, tenant_id, quick_answer_id, *, user_id=None) -> None:
    """Delete one of this tenant's quick answers. The history keeps it, so it can be undone.
    A button pointing at it just stops matching, and the AI answers instead."""
    with conn.transaction():
        _as_user(conn, user_id)
        deleted = conn.execute(
            "DELETE FROM quick_answers WHERE tenant_id = %s AND id = %s RETURNING id",
            (tenant_id, quick_answer_id),
        ).fetchone()
        if deleted is None:
            raise QuickAnswerError("quick answer not found")


UNDO_TARGET = """
SELECT h.quick_answer_id, h.operation, h.before,
       (SELECT max(l.id) FROM quick_answer_history AS l
        WHERE l.quick_answer_id = h.quick_answer_id) AS latest
FROM quick_answer_history AS h
WHERE h.tenant_id = %s AND h.id = %s
"""
RESTORE_DELETED = """
INSERT INTO quick_answers OVERRIDING SYSTEM VALUE
SELECT * FROM jsonb_populate_record(NULL::quick_answers, %s)
"""
RESTORE_EDITED = """
UPDATE quick_answers AS q
SET (code, triggers, answers, buttons, action, active) =
    (r.code, r.triggers, r.answers, r.buttons, r.action, r.active)
FROM jsonb_populate_record(NULL::quick_answers, %s) AS r
WHERE q.id = r.id
"""


def undo_change(conn, tenant_id, history_id, *, user_id=None) -> int:
    """Undo one recorded change of this tenant: a create is deleted, an edit reverted,
    a delete re-created with the same id. Only the latest change of that quick answer can be
    undone (undo newer ones first), so an undo never silently overwrites a later edit.
    The undo is itself recorded, so it can be undone too. Returns the quick answer's id."""
    with conn.transaction():
        conn.execute(
            "SELECT pg_advisory_xact_lock(%s, mod(%s, 2147483647)::integer)",
            (TENANT_LOCK, tenant_id),
        )  # two admins undoing at once: one waits
        _as_user(conn, user_id)
        target = conn.execute(UNDO_TARGET, (tenant_id, history_id)).fetchone()
        if target is None:
            raise QuickAnswerError("change not found")
        quick_answer_id, operation, before, latest = target
        if latest != history_id:
            raise QuickAnswerError(
                "this quick answer was changed again after that; undo the newer change first"
            )
        try:
            if operation == "insert":
                conn.execute("DELETE FROM quick_answers WHERE id = %s", (quick_answer_id,))
            elif operation == "delete":
                conn.execute(RESTORE_DELETED, (Jsonb(before),))
            else:
                conn.execute(RESTORE_EDITED, (Jsonb(before),))
        except errors.UniqueViolation as error:
            raise _friendly(error, before["code"]) from None
        return quick_answer_id
