"""Website chat API (P5.1), used by the widget.

    POST    /api/chat/{slug}       {"visitor", "text" | "payload", "id"?} -> one SSE "reply" event
    OPTIONS /api/chat/{slug}       the browser's permission check before the POST
    GET     /api/chat/{slug}/poll  ?visitor=…&after=ID -> newer messages (staff replies, history)

Only pages on the company's allowed origins may call it (browsers send Origin; a sandboxed
page or a local file sends "null", which is refused). Allowed origins are exact
("https://example.com") or cover subdomains ("https://*.example.com", not the bare domain).

The reply is worked out and stored before the first byte is sent, so a visitor who closes
the page mid-reply loses nothing: the reply is there on the next poll.
"""

import collections
import datetime
import json
import math
import re
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.engine import Inbound

MAX_TEXT = 1000  # F8: same cap as the AI prompt (MAX_STUDENT_CHARS)
VISITOR = re.compile(r"[A-Za-z0-9_-]{16,64}")  # random id from the widget: long enough not to guess
PAYLOAD = re.compile(r"[A-Z][A-Z0-9_]{1,39}")  # quick answer codes (migration 003)
MESSAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
FIELDS = {"visitor", "text", "payload", "id"}
PER_VISITOR = 10  # messages a minute (F8)
PER_IP = 30  # a minute: several students may share one office or phone network
POLL_LIMIT = 50

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
    """(tenant id, web channel id, allowed origins), or None if there's no live web chat."""
    with request.app.state.pool.connection() as conn:
        return conn.execute(
            "SELECT t.id, ch.id, t.allowed_origins FROM tenants t"
            " JOIN channels ch ON ch.tenant_id = t.id AND ch.type = 'web' AND ch.active"
            " WHERE t.slug = %s AND t.active",
            (slug,),
        ).fetchone()


def _cors(origin: str) -> dict:
    return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}


def _error(status: int, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status, headers=headers)


def _check(request: Request, slug: str):
    """(company, CORS headers, None), or (None, None, the error response)."""
    company = _company(request, slug)
    if company is None:
        return None, None, _error(404, "no chat here")
    origin = request.headers.get("origin")
    if not origin_allowed(origin, company[2]):
        return None, None, _error(403, "this website may not use this chat")
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
        return _error(429, "too many messages, wait a moment", headers | {"Retry-After": str(wait)})
    try:
        data = json.loads(await request.body())
    except ValueError:  # includes bad UTF-8
        return _error(400, "the body isn't valid JSON", headers)
    if problem := _message(data):
        return _error(400, problem, headers)
    if wait := state.per_visitor.wait((slug, data["visitor"])):
        return _error(429, "too many messages, wait a moment", headers | {"Retry-After": str(wait)})

    event = await run_in_threadpool(_reply, state, company, data)
    frame = "event: reply" + chr(10) + "data: " + json.dumps(event, ensure_ascii=False)
    return StreamingResponse(
        iter([frame + chr(10) * 2]),
        media_type="text/event-stream",
        headers=headers | {"Cache-Control": "no-store"},
    )


def _reply(state, company, data) -> dict:
    """Runs the engine; the reply is stored when this returns."""
    tenant_id, channel_id, _ = company
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
    # ponytail: the whole reply in one event (replies are 1-4 sentences); token streaming
    # can add "delta" events later without changing this format.
    return {"text": reply.text, "buttons": list(reply.buttons), "after": after}


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
    messages = [{"id": i, "role": role, "text": text} for i, role, text in rows]
    return JSONResponse({"messages": messages}, headers=headers | {"Cache-Control": "no-store"})
