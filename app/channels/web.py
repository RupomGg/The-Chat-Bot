"""Website chat API (P5.1), used by the widget.

    POST    /api/chat/{slug}       {"visitor", "text" | "payload", "id"?} -> one SSE "reply" event
    OPTIONS /api/chat/{slug}       the browser's permission check before the POST
    GET     /api/chat/{slug}/poll  ?visitor=…&after=ID -> newer messages (staff replies, history)
    GET     /api/widget-config/{slug}  name, colour, greeting, buttons, privacy link (P5.2)
    GET     /widget.js, /demo          the widget script, and a page to try it on (P5.2)

Only pages on the company's allowed origins may call it (browsers send Origin; a sandboxed
page or a local file sends "null", which is refused). Allowed origins are exact
("https://example.com") or cover subdomains ("https://*.example.com", not the bare domain).
Our own pages (the demo) may always use it.

The reply is worked out and stored before the first byte is sent, so a visitor who closes
the page mid-reply loses nothing: the reply is there on the next poll.
"""

import collections
import datetime
import json
import math
import pathlib
import re
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from app.contact_details import normalize_https_url
from app.engine import Inbound

MAX_TEXT = 1000  # F8: same cap as the AI prompt (MAX_STUDENT_CHARS)
VISITOR = re.compile(r"[A-Za-z0-9_-]{16,64}")  # random id from the widget: long enough not to guess
PAYLOAD = re.compile(r"[A-Z][A-Z0-9_]{1,39}")  # quick answer codes (migration 003)
MESSAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
FIELDS = {"visitor", "text", "payload", "id"}
PER_VISITOR = 10  # messages a minute (F8)
PER_IP = 30  # a minute: several students may share one office or phone network
POLL_LIMIT = 50
STATIC = pathlib.Path(__file__).resolve().parent.parent / "static"
COLOR = re.compile(r"#[0-9a-fA-F]{6}")
WHATSAPP = re.compile(r"[1-9][0-9]{7,14}")  # wa.me number: country code, no +
MESSENGER = re.compile(r"[A-Za-z0-9.]{5,50}")  # m.me page username
MAX_GREETING = 300
MAX_CHIPS = 4
# Refusals are readable by any website (they carry no data), so a widget on a site that isn't
# allowed sees "403" and stops, instead of taking it for a network drop and retrying forever.
REFUSED = {"Access-Control-Allow-Origin": "*"}

router = APIRouter()


class RateLimit:
    """At most `limit` hits per key in any `window` seconds.

    ponytail: kept in this process's memory; with several web processes each allows the
    limit (Cloudflare limits /api/chat in front, PRD §12). Move to the database if that matters.
    """

    def __init__(self, limit: int, window: float = 60.0, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.hits: dict = {}

    def wait(self, key) -> int:
        """0 and counts the hit if allowed, else the seconds until it would be."""
        now = self.clock()
        if len(self.hits) > 10_000:  # forget keys that went quiet
            self.hits = {k: q for k, q in self.hits.items() if now - q[-1] < self.window}
        hits = self.hits.setdefault(key, collections.deque())
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return math.ceil(self.window - (now - hits[0]))  # at least 1: hits[0] is in the window
        hits.append(now)
        return 0


def origin_allowed(origin: str | None, allowed: list[str]) -> bool:
    if not origin:  # "null" (local file, sandboxed frame) fails the exact-form check
        return False
    parts = urlsplit(origin)
    try:
        port = parts.port
    except ValueError:
        return False
    if origin != f"{parts.scheme}://{parts.netloc}" or "@" in parts.netloc or not parts.hostname:
        return False  # browsers send only scheme://host[:port]
    for entry in allowed:
        rule = urlsplit(entry)
        if rule.scheme != parts.scheme or rule.port != port or not rule.hostname:
            continue
        if rule.hostname.startswith("*."):
            if parts.hostname.endswith(rule.hostname[1:]):
                return True
        elif parts.hostname == rule.hostname:
            return True
    return False


def _company(request: Request, slug: str):
    """(tenant id, web channel id, allowed origins, name, widget theme), or None if there's
    no live web chat."""
    with request.app.state.pool.connection() as conn:
        return conn.execute(
            "SELECT t.id, ch.id, t.allowed_origins, t.name, t.widget_theme FROM tenants t"
            " JOIN channels ch ON ch.tenant_id = t.id AND ch.type = 'web' AND ch.active"
            " WHERE t.slug = %s AND t.active",
            (slug,),
        ).fetchone()


def _cors(origin: str) -> dict:
    return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}


def _retry(wait: int) -> dict:
    # Exposed, or the widget on another website couldn't read it (CORS hides most headers).
    return {"Retry-After": str(wait), "Access-Control-Expose-Headers": "Retry-After"}


def _error(status: int, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status, headers=headers)


def _check(request: Request, slug: str):
    """(company, CORS headers, None), or (None, None, the error response)."""
    company = _company(request, slug)
    if company is None:
        return None, None, _error(404, "no chat here", REFUSED)
    origin = request.headers.get("origin")
    if origin is None and request.method == "GET":
        # Our own page: browsers leave Origin off same-origin GETs (and Sec-Fetch-Site too, on
        # plain http, e.g. the demo on a phone). Another site's script always sends Origin, and
        # a GET changes nothing, so allowing it costs nothing a faked Origin couldn't get.
        return company, {}, None
    own = str(request.base_url).rstrip("/")
    if origin != own and not origin_allowed(origin, company[2]):
        return None, None, _error(403, "this website may not use this chat", REFUSED)
    return company, _cors(origin), None


def _message(body) -> str | None:
    """What's wrong with the request body, or None."""
    if not isinstance(body, dict) or not body.keys() <= FIELDS:
        return "expected an object with visitor, text or payload, and id"
    visitor, text, payload, mid = (body.get(k) for k in ("visitor", "text", "payload", "id"))
    if not isinstance(visitor, str) or not VISITOR.fullmatch(visitor):
        return "visitor must be 16-64 letters, digits, - or _"
    if (text is None) == (payload is None):
        return "send either text or payload"
    if text is not None and (not isinstance(text, str) or not text.strip()):
        return "text must be a non-empty string"
    if text is not None and len(text) > MAX_TEXT:
        return f"text is longer than {MAX_TEXT} characters"
    if payload is not None and (not isinstance(payload, str) or not PAYLOAD.fullmatch(payload)):
        return "payload must be a button code"
    if mid is not None and (not isinstance(mid, str) or not MESSAGE_ID.fullmatch(mid)):
        return "id must be 1-64 letters, digits, - or _"
    return None


def _latest_id(conn, channel_id: int, visitor: str) -> int:
    return conn.execute(
        "SELECT coalesce(max(m.id), 0) FROM messages m"
        " JOIN conversations cv ON cv.id = m.conversation_id"
        " JOIN contacts c ON c.id = cv.contact_id"
        " WHERE c.channel_id = %s AND c.external_user_id = %s",
        (channel_id, visitor),
    ).fetchone()[0]


@router.options("/api/chat/{slug}")
def preflight(slug: str, request: Request):
    company, headers, error = _check(request, slug)
    if error:
        return error
    headers |= {
        "Access-Control-Allow-Methods": "POST, GET",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "600",
    }
    return Response(status_code=204, headers=headers)


@router.post("/api/chat/{slug}")
async def chat(slug: str, request: Request):
    company, headers, error = await run_in_threadpool(_check, request, slug)
    if error:
        return error
    state = request.app.state
    ip = getattr(request.client, "host", "unknown")  # no client address on a Unix socket
    if wait := state.per_ip.wait((slug, ip)):
        return _error(429, "too many messages, wait a moment", headers | _retry(wait))
    try:
        data = json.loads(await request.body())
    except ValueError:  # includes bad UTF-8
        return _error(400, "the body isn't valid JSON", headers)
    if problem := _message(data):
        return _error(400, problem, headers)
    if wait := state.per_visitor.wait((slug, data["visitor"])):
        return _error(429, "too many messages, wait a moment", headers | _retry(wait))

    event = await run_in_threadpool(_reply, state, company, data)
    frame = "event: reply" + chr(10) + "data: " + json.dumps(event, ensure_ascii=False)
    return StreamingResponse(
        iter([frame + chr(10) * 2]),
        media_type="text/event-stream",
        headers=headers | {"Cache-Control": "no-store"},
    )


def _reply(state, company, data) -> dict:
    """Runs the engine; the reply is stored when this returns."""
    tenant_id, channel_id = company[:2]
    now = datetime.datetime.now(datetime.UTC)
    msg = Inbound(
        tenant_id,
        channel_id,
        data["visitor"],
        now,
        text=data.get("text"),
        payload=data.get("payload"),
        external_id=data.get("id"),
    )
    with state.pool.connection() as conn:
        reply = state.engine.handle(conn, msg, now=now)
        after = _latest_id(conn, channel_id, data["visitor"])
        buttons = _buttons(conn, tenant_id, reply.buttons)
    # ponytail: the whole reply in one event (replies are 1-4 sentences); token streaming
    # can add "delta" events later without changing this format.
    # waiting: a person has this chat, so the bot stays quiet; the widget says so once.
    waiting = reply.source == "silent"
    return {"text": reply.text, "buttons": buttons, "after": after, "waiting": waiting}


def _buttons(conn, tenant_id: int, codes) -> list[dict]:
    """Codes with a label to show: the quick answer's first trigger phrase ("Fees").

    ponytail: no label column yet; add one when an admin needs a label that isn't a trigger
    (Messenger and WhatsApp button titles may want it, P5.3-P5.4).
    """
    rows = conn.execute(
        "SELECT code, triggers[1] FROM quick_answers WHERE tenant_id = %s AND code = ANY(%s)",
        (tenant_id, list(codes)),
    ).fetchall()
    first = {code: trigger for code, trigger in rows if trigger}
    labels = {code: first.get(code, code.replace("_", " ").lower()) for code in codes}
    return [{"code": code, "label": labels[code][:20].capitalize()} for code in codes]


@router.get("/api/chat/{slug}/poll")
def poll(slug: str, request: Request, visitor: str = "", after: int = 0):
    company, headers, error = _check(request, slug)
    if error:
        return error
    if not VISITOR.fullmatch(visitor):
        return _error(400, "visitor must be 16-64 letters, digits, - or _", headers)
    with request.app.state.pool.connection() as conn:
        rows = conn.execute(
            "SELECT m.id, m.role, m.content FROM messages m"
            " JOIN conversations cv ON cv.id = m.conversation_id"
            " JOIN contacts c ON c.id = cv.contact_id"
            " WHERE c.channel_id = %s AND c.external_user_id = %s AND m.id > %s"
            " AND m.role IN ('student', 'bot', 'staff') ORDER BY m.id LIMIT %s",
            (company[1], visitor, after, POLL_LIMIT),
        ).fetchall()
        # A tap is stored as "[button FEES]"; the visitor saw the button's label, so show that.
        taps = {_tap(text) for _, role, text in rows if role == "student"} - {None}
        labels = {b["code"]: b["label"] for b in _buttons(conn, company[0], sorted(taps))}
    messages = [
        {"id": i, "role": role, "text": labels.get(_tap(text) if role == "student" else None, text)}
        for i, role, text in rows
    ]
    return JSONResponse({"messages": messages}, headers=headers | {"Cache-Control": "no-store"})


def _tap(text: str) -> str | None:
    """The button code if this is how the engine stores a tap ("[button FEES]")."""
    code = text[8:-1] if text.startswith("[button ") and text.endswith("]") else ""
    return code if PAYLOAD.fullmatch(code) else None


def _valid(value, pattern: re.Pattern) -> str | None:
    """A theme value only if it's safe to put in the page (bad ones fall back to defaults)."""
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


@router.get("/api/widget-config/{slug}")
def widget_config(slug: str, request: Request):
    company, headers, error = _check(request, slug)
    if error:
        return error
    tenant_id, _, _, name, theme = company
    greeting = theme.get("greeting")
    chips = theme.get("chips")
    with request.app.state.pool.connection() as conn:
        if not isinstance(chips, list):  # default: the company's first quick answers
            chips = [
                code
                for (code,) in conn.execute(
                    "SELECT code FROM quick_answers WHERE tenant_id = %s AND active ORDER BY id",
                    (tenant_id,),
                )
            ]
        chips = [c for c in chips if isinstance(c, str) and PAYLOAD.fullmatch(c)][:MAX_CHIPS]
        buttons = _buttons(conn, tenant_id, chips)
    config = {
        "name": name,
        "color": _valid(theme.get("color"), COLOR) or "#0f766e",
        "greeting": greeting
        if isinstance(greeting, str) and 0 < len(greeting.strip()) <= MAX_GREETING
        else "Hi! How can we help you today?",
        "buttons": buttons,
        "privacy_url": normalize_https_url(theme.get("privacy_url"))
        or request.app.state.config.public_base_url + "/privacy",
        "whatsapp": _valid(theme.get("whatsapp"), WHATSAPP),
        "messenger": _valid(theme.get("messenger"), MESSENGER),
    }
    return JSONResponse(config, headers=headers | {"Cache-Control": "no-store"})


@router.get("/widget.js")
def widget_js():
    return FileResponse(
        STATIC / "widget.js",
        media_type="text/javascript; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},  # a fix reaches every site in 5 min
    )


@router.get("/demo")
def demo_page():
    """A page to try the widget on, here and on phones (the P5.2 device check)."""
    return FileResponse(STATIC / "demo.html", media_type="text/html; charset=utf-8")
