"""The AI's tools (PRD §9.4, D-020): the only actions the AI can take during a chat.

Every input is validated here again (the API's strict schemas are not trusted alone). A tool
only ever touches the current contact and conversation, which come from the engine, never
from the AI: no schema has an id for another contact. Bad input never raises; the result
tells the AI what to fix. Results are small JSON; `effects` tell the engine what happened
(e.g. "became_hot", "handoff") so it can notify people.
"""

import datetime
import json
import zoneinfo
from dataclasses import dataclass

from psycopg import sql
from psycopg.types.json import Jsonb

from app import booking, scoring
from app.contact_details import normalize_email, normalize_name, normalize_year_month
from app.packs import CORE_HANDOFF_REASONS, Pack
from app.phones import normalize_phone
from app.prompts import compact_json

UTC = datetime.UTC
MAX_TEXT = 500
MAX_LIST_ITEMS = 20
MAX_SUMMARY = 1000
SLOTS_SHOWN = 5
ALTERNATIVES = 3
CONTACT_COLUMNS = ("name", "phone", "email", "adult")  # stored on contacts, not in profile
BOOKABLE_FROM = ("new", "contacted", "qualified", "lost")  # later stages keep their status


class ToolInputError(ValueError):
    """The AI sent something we can't use; the message goes back to it."""


@dataclass(frozen=True)
class ToolContext:
    conn: object
    tenant_id: int
    contact_id: int
    conversation_id: int
    pack: Pack
    settings: dict  # the tenant's pack settings
    now: datetime.datetime
    timezone: str
    country: str = "BD"  # for phone numbers without a country code
    pause_hours: int = 24  # how long the bot stays quiet after a handoff


@dataclass(frozen=True)
class ToolResult:
    content: dict  # sent back to the AI
    is_error: bool = False
    effects: tuple = ()  # for the engine: "profile_updated", "became_hot", "booked", …


def _error(message: str, **extra) -> ToolResult:
    return ToolResult({"error": message} | extra, is_error=True)


def _check_keys(args: dict, allowed: set, required: set) -> None:
    unknown = sorted(set(args) - allowed)
    if unknown:
        raise ToolInputError(f"unknown field(s): {', '.join(unknown)}")
    missing = sorted(required - set(args))
    if missing:
        raise ToolInputError(f"missing: {', '.join(missing)}")


# ---------- schemas ----------

FIELD_TYPES = {
    "text": {"type": "string"},
    "int": {"type": "integer"},
    "bool": {"type": "boolean"},
    "list": {"type": "array", "items": {"type": "string"}},
    "yearmonth": {"type": "string"},
}


def _object(properties: dict, required=()) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _tool(name: str, description: str, schema: dict) -> dict:
    return {"name": name, "description": description, "input_schema": schema, "strict": True}


def schemas(pack: Pack) -> list[dict]:
    """The tool definitions for this industry, in the order the AI should think of them."""
    profile = {
        "name": {"type": "string", "description": "Full name"},
        "phone": {"type": "string", "description": "Phone number as given"},
        "email": {"type": "string", "description": "Email address"},
        "adult": {"type": "boolean", "description": "18 or older"},
    }
    for f in pack.fields:
        schema = (
            {"type": "string", "enum": list(f.choices)}
            if f.type == "choice"
            else dict(FIELD_TYPES[f.type])
        )
        suffix = " (YYYY-MM)" if f.type == "yearmonth" else ""
        profile[f.name] = schema | {"description": f.label["en"] + suffix}
    appointment = pack.terms["appointment"]["en"].lower()
    reasons = list(CORE_HANDOFF_REASONS) + list(pack.handoff_reasons)
    contact = {"name": {"type": "string"}, "phone": {"type": "string"}}
    return [
        _tool(
            "update_profile",
            "Save what the customer told you about themselves, exactly as they said it. "
            "Send only the fields they gave. The result says what was saved or what to fix.",
            _object(profile),
        ),
        _tool(
            "list_slots",
            f"Open times for a {appointment}. Leave out branch for all branches.",
            _object(
                {
                    "branch": {"type": "string", "description": "Branch name, or Online"},
                    "from_date": {"type": "string", "description": "YYYY-MM-DD, default today"},
                }
            ),
        ),
        _tool(
            "book_appointment",
            f"Book a {appointment} in a slot from list_slots, after the customer confirmed "
            "the time, their name and phone.",
            _object({"slot_id": {"type": "string"}} | contact, ("slot_id", "name", "phone")),
        ),
        _tool(
            "register_event",
            "Register the customer for an event listed in the knowledge.",
            _object({"event_id": {"type": "integer"}} | contact, ("event_id", "name", "phone")),
        ),
        _tool(
            "log_unanswered",
            "Record a question the knowledge doesn't answer, before saying the team will confirm.",
            _object({"question": {"type": "string"}}, ("question",)),
        ),
        _tool(
            "off_topic",
            "Call this whenever you decline a request outside this business.",
            _object({}),
        ),
        _tool(
            "request_handoff",
            "Hand the conversation to a person, with a short summary for them.",
            _object(
                {"reason": {"type": "string", "enum": reasons}, "summary": {"type": "string"}},
                ("reason", "summary"),
            ),
        ),
    ]


# ---------- values ----------


def _text(value, limit=MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolInputError("must be non-empty text")
    return " ".join(value.split())[:limit]


def _contact_value(ctx: ToolContext, key: str, value):
    if key == "adult":
        if not isinstance(value, bool):
            raise ToolInputError("must be true or false")
        return value
    normalize = {
        "name": normalize_name,
        "email": normalize_email,
        "phone": lambda v: normalize_phone(v, ctx.country) if isinstance(v, str) else None,
    }[key]
    clean = normalize(value)
    if clean is None:
        hint = {
            "name": "not a name",
            "email": "not a valid email address",
            "phone": "not a valid phone number: ask for a mobile number, e.g. 01712345678, "
            "or one with a country code, e.g. +44 7700 900123",
        }[key]
        raise ToolInputError(hint)
    return clean


def _field_value(field, value):
    kind = field.type
    if kind == "text":
        return _text(value)
    if kind == "int":
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 1000:
            raise ToolInputError("must be a whole number from 0 to 1000")
        return value
    if kind == "bool":
        if not isinstance(value, bool):
            raise ToolInputError("must be true or false")
        return value
    if kind == "choice":
        match = next(
            (c for c in field.choices if isinstance(value, str) and value.strip().casefold() == c),
            None,
        )
        if match is None:
            raise ToolInputError(f"must be one of: {', '.join(field.choices)}")
        return match
    if kind == "list":
        if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
            raise ToolInputError(f"must be a list of up to {MAX_LIST_ITEMS} items")
        items: list[str] = []
        for item in value:
            clean = _text(item, 100)
            if clean.casefold() not in {i.casefold() for i in items}:
                items.append(clean)
        return items
    clean = normalize_year_month(value)  # yearmonth
    if clean is None:
        raise ToolInputError("must be a month like 2027-01")
    return clean


# ---------- saving the profile (and rescoring) ----------


def _save(ctx: ToolContext, columns: dict, profile: dict) -> tuple:
    """Write contact columns and profile fields, rescore; returns the effects."""
    conn = ctx.conn
    old = conn.execute(
        "SELECT score FROM contacts WHERE tenant_id = %s AND id = %s FOR UPDATE",
        (ctx.tenant_id, ctx.contact_id),
    ).fetchone()
    if old is None:
        raise ToolInputError("contact not found")
    sets = [sql.SQL("profile = profile || %s")] + [
        sql.SQL("{} = %s").format(sql.Identifier(c)) for c in columns
    ]
    row = conn.execute(
        sql.SQL(
            "UPDATE contacts SET {} WHERE tenant_id = %s AND id = %s"
            " RETURNING name, phone, adult, profile"
        ).format(sql.SQL(", ").join(sets)),
        (Jsonb(profile), *columns.values(), ctx.tenant_id, ctx.contact_id),
    ).fetchone()
    name, phone, adult, stored = row
    today = ctx.now.astimezone(_zone(ctx)).date()
    result = scoring.score(
        ctx.pack, stored | {"name": name, "phone": phone, "adult": adult}, ctx.settings, today
    )
    conn.execute(
        "UPDATE contacts SET score = %s, flags = %s WHERE tenant_id = %s AND id = %s",
        (result.level, list(result.flags), ctx.tenant_id, ctx.contact_id),
    )
    effects = ("profile_updated",)
    if result.level == "hot" and old[0] != "hot":
        effects += ("became_hot",)
    return effects


def _zone(ctx: ToolContext) -> zoneinfo.ZoneInfo:
    return zoneinfo.ZoneInfo(ctx.timezone)


def update_profile(ctx: ToolContext, args: dict) -> ToolResult:
    fields = {f.name: f for f in ctx.pack.fields}
    _check_keys(args, set(fields) | set(CONTACT_COLUMNS), set())
    if not args:
        return ToolResult({"saved": []})
    columns, profile, problems = {}, {}, []
    for key, value in args.items():
        try:
            if key in CONTACT_COLUMNS:
                columns[key] = _contact_value(ctx, key, value)
            else:
                profile[key] = _field_value(fields[key], value)
        except ToolInputError as error:
            problems.append(f"{key}: {error}")
    if problems:
        raise ToolInputError("nothing saved; fix: " + "; ".join(problems))
    with ctx.conn.transaction():
        effects = _save(ctx, columns, profile)
    return ToolResult({"saved": sorted(args)}, effects=effects)


# ---------- slots and bookings ----------


def _branches(ctx: ToolContext) -> dict:
    rows = ctx.conn.execute(
        "SELECT id, name FROM branches WHERE tenant_id = %s ORDER BY id", (ctx.tenant_id,)
    )
    return dict(rows.fetchall())


def _slot_id(slot) -> str:
    return f"{slot.branch_id}@{slot.start.astimezone(UTC):%Y-%m-%dT%H:%MZ}"


def _parse_slot_id(value) -> tuple:
    try:
        branch, when = value.split("@")
        start = datetime.datetime.strptime(when, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
        return int(branch), start
    except (AttributeError, ValueError):
        raise ToolInputError("slot_id must be one returned by list_slots") from None


def _slot_json(slot, names: dict) -> dict:
    return {
        "slot_id": _slot_id(slot),
        "branch": names.get(slot.branch_id, "?"),
        "start": f"{slot.start:%a %d %b %H:%M}",
        "seats_left": slot.remaining,
    }


def _open_slots(ctx: ToolContext, limit: int, **kwargs) -> list:
    names = _branches(ctx)
    found = booking.list_slots(ctx.conn, ctx.tenant_id, now=ctx.now, limit=limit, **kwargs)
    return [_slot_json(s, names) for s in found]


def list_slots(ctx: ToolContext, args: dict) -> ToolResult:
    _check_keys(args, {"branch", "from_date"}, set())
    kwargs = {}
    if "branch" in args:
        names = _branches(ctx)
        wanted = args["branch"].strip().casefold() if isinstance(args["branch"], str) else None
        match = next((i for i, n in names.items() if n.casefold() == wanted), None)
        if match is None:
            raise ToolInputError(f"unknown branch; choose one of: {', '.join(names.values())}")
        kwargs["branch_id"] = match
    if "from_date" in args:
        try:
            kwargs["from_date"] = datetime.date.fromisoformat(args["from_date"])
        except (TypeError, ValueError):
            raise ToolInputError("from_date must be YYYY-MM-DD") from None
    slots = _open_slots(ctx, SLOTS_SHOWN, **kwargs)
    content = {"slots": slots, "timezone": ctx.timezone}
    if not slots:
        content["note"] = "no open times in the next two weeks"
    return ToolResult(content)


def book_appointment(ctx: ToolContext, args: dict) -> ToolResult:
    _check_keys(args, {"slot_id", "name", "phone"}, {"slot_id", "name", "phone"})
    branch_id, start = _parse_slot_id(args["slot_id"])
    problems, columns = [], {}
    for key in ("name", "phone"):
        try:
            columns[key] = _contact_value(ctx, key, args[key])
        except ToolInputError as error:
            problems.append(f"{key}: {error}")
    if problems:
        raise ToolInputError("not booked; fix: " + "; ".join(problems))
    with ctx.conn.transaction():
        effects = _save(ctx, columns, {})
        try:
            booking_id = booking.book(
                ctx.conn, ctx.tenant_id, ctx.contact_id, branch_id, start, now=ctx.now
            )
        except booking.BookingError as error:
            known = branch_id in _branches(ctx)
            alternatives = _open_slots(
                ctx, ALTERNATIVES, **({"branch_id": branch_id} if known else {})
            )
            result = _error(f"not booked: {error}", alternatives=alternatives)
            return ToolResult(result.content, is_error=True, effects=effects)
        ctx.conn.execute(
            "UPDATE contacts SET status = 'booked'"
            " WHERE tenant_id = %s AND id = %s AND status = ANY (%s)",
            (ctx.tenant_id, ctx.contact_id, list(BOOKABLE_FROM)),
        )
    local = start.astimezone(_zone(ctx))
    content = {
        "booked": True,
        "booking_id": booking_id,
        "branch": _branches(ctx)[branch_id],
        "start": f"{local:%a %d %b %H:%M}",
    }
    return ToolResult(content, effects=(*effects, "booked"))


# ---------- events ----------


def _upcoming_events(ctx: ToolContext) -> list:
    rows = ctx.conn.execute(
        "SELECT id, title, starts_at FROM events WHERE tenant_id = %s AND starts_at > %s"
        " ORDER BY starts_at LIMIT 5",
        (ctx.tenant_id, ctx.now),
    ).fetchall()
    zone = _zone(ctx)
    return [
        {"event_id": i, "title": t, "starts": f"{s.astimezone(zone):%a %d %b %H:%M}"}
        for i, t, s in rows
    ]


def register_event(ctx: ToolContext, args: dict) -> ToolResult:
    _check_keys(args, {"event_id", "name", "phone"}, {"event_id", "name", "phone"})
    event_id = args["event_id"]
    if not isinstance(event_id, int) or isinstance(event_id, bool):
        raise ToolInputError("event_id must be a number from the event list")
    columns = {k: _contact_value(ctx, k, args[k]) for k in ("name", "phone")}
    conn = ctx.conn
    with conn.transaction():
        event = conn.execute(
            "SELECT title, starts_at, capacity FROM events"
            " WHERE tenant_id = %s AND id = %s FOR UPDATE",
            (ctx.tenant_id, event_id),
        ).fetchone()
        if event is None or event[1] <= ctx.now:
            return _error("no upcoming event with that id", upcoming=_upcoming_events(ctx))
        title, starts_at, capacity = event
        effects = _save(ctx, columns, {})
        status = conn.execute(
            "SELECT status FROM event_registrations WHERE event_id = %s AND contact_id = %s",
            (event_id, ctx.contact_id),
        ).fetchone()
        starts = f"{starts_at.astimezone(_zone(ctx)):%a %d %b %H:%M}"
        if status is not None and status[0] == "registered":
            return ToolResult(
                {"registered": True, "event": title, "starts": starts}, effects=effects
            )
        taken = conn.execute(
            "SELECT count(*) FROM event_registrations"
            " WHERE event_id = %s AND status = 'registered'",
            (event_id,),
        ).fetchone()[0]
        if capacity is not None and taken >= capacity:
            return ToolResult({"error": "that event is full"}, is_error=True, effects=effects)
        conn.execute(
            "INSERT INTO event_registrations (tenant_id, event_id, contact_id) VALUES (%s, %s, %s)"
            " ON CONFLICT (event_id, contact_id) DO UPDATE SET status = 'registered'",
            (ctx.tenant_id, event_id, ctx.contact_id),
        )
    content = {"registered": True, "event": title, "starts": starts}
    return ToolResult(content, effects=(*effects, "registered"))


# ---------- conversation signals ----------


def _event(ctx: ToolContext, kind: str, detail: dict) -> None:
    ctx.conn.execute(
        "INSERT INTO audit_events (tenant_id, conversation_id, kind, detail)"
        " VALUES (%s, %s, %s, %s)",
        (ctx.tenant_id, ctx.conversation_id, kind, Jsonb(detail)),
    )


def log_unanswered(ctx: ToolContext, args: dict) -> ToolResult:
    _check_keys(args, {"question"}, {"question"})
    question = _text(args["question"])
    with ctx.conn.transaction():
        _event(ctx, "unanswered", {"question": question})
        ctx.conn.execute(
            "UPDATE conversations SET unanswered_streak = unanswered_streak + 1"
            " WHERE tenant_id = %s AND id = %s",
            (ctx.tenant_id, ctx.conversation_id),
        )
    return ToolResult({"logged": True}, effects=("unanswered",))


def off_topic(ctx: ToolContext, args: dict) -> ToolResult:
    _check_keys(args, set(), set())
    with ctx.conn.transaction():
        _event(ctx, "off_topic", {})
    return ToolResult({"logged": True}, effects=("off_topic",))


def request_handoff(ctx: ToolContext, args: dict) -> ToolResult:
    _check_keys(args, {"reason", "summary"}, {"reason", "summary"})
    reasons = CORE_HANDOFF_REASONS + ctx.pack.handoff_reasons
    if args["reason"] not in reasons:
        raise ToolInputError(f"reason must be one of: {', '.join(reasons)}")
    summary = _text(args["summary"], MAX_SUMMARY)
    with ctx.conn.transaction():
        row = ctx.conn.execute(
            "SELECT state FROM conversations WHERE tenant_id = %s AND id = %s FOR UPDATE",
            (ctx.tenant_id, ctx.conversation_id),
        ).fetchone()
        if row is None:
            raise ToolInputError("conversation not found")
        if row[0] == "human":
            return ToolResult({"handoff": "already with a person"})  # one handoff, not two
        ctx.conn.execute(
            "UPDATE conversations SET state = 'human', paused_until = %s"
            " WHERE tenant_id = %s AND id = %s",
            (
                ctx.now + datetime.timedelta(hours=ctx.pause_hours),
                ctx.tenant_id,
                ctx.conversation_id,
            ),
        )
        _event(ctx, "handoff", {"reason": args["reason"], "summary": summary})
    return ToolResult({"handoff": True}, effects=("handoff",))


# ---------- running a call ----------

TOOLS = {
    "update_profile": update_profile,
    "list_slots": list_slots,
    "book_appointment": book_appointment,
    "register_event": register_event,
    "log_unanswered": log_unanswered,
    "off_topic": off_topic,
    "request_handoff": request_handoff,
}


def run(ctx: ToolContext, call) -> ToolResult:
    """Run one tool call from the AI. Never raises for bad input: returns an error result."""
    tool = TOOLS.get(call.name)
    if tool is None:
        return _error(f"unknown tool {call.name!r}")
    args = call.input
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return _error("input is not valid JSON")
    if not isinstance(args, dict):
        return _error("input must be a JSON object")
    try:
        return tool(ctx, args)
    except ToolInputError as error:
        return _error(str(error))


def result_block(call, result: ToolResult) -> dict:
    """The tool_result block to send back (Claude's format; the Gemini path converts it)."""
    return {
        "type": "tool_result",
        "tool_use_id": call.id,
        "content": compact_json(result.content),
        "is_error": result.is_error,
    }
