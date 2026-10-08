"""Facebook Messenger (P5.3): Meta's webhook in, the Graph API out.

    GET  /webhooks/meta   Meta's check when a webhook is set up (our verify token)
    POST /webhooks/meta   events, signed with the app secret of the Page's own app (each client
                          has its own app, PRD §7); each event becomes a job, Meta gets 200 at once

The worker runs the jobs: `messenger_event` (the engine decides the reply; the reply is queued
as `messenger_send` in the same transaction, so a crash can't lose it) and `messenger_send`
(the Graph API call, retried only when retrying can help).
"""

import datetime
import functools
import json

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from psycopg.types.json import Jsonb

from app import jobs
from app.engine import Inbound
from app.quick_answers import button_labels
from app.security import decrypt, encrypt, verify_meta_signature

GRAPH = "https://graph.facebook.com/v26.0"  # newest, 2026-07-29 (v25.0 runs until 2028-07-29)
WINDOW = datetime.timedelta(hours=24)  # Meta: a business may reply for 24 h after a message
MAX_TEXT = 2000  # Messenger's limit
MAX_QUICK_REPLIES = 13
SEND_ATTEMPTS = 5
RETRY_CODES = {1, 2, 4, 17, 32, 613}  # Meta's temporary and rate-limit errors
UNAVAILABLE_CODES = {551}  # this person isn't available (blocked the Page, deactivated)
OUTSIDE_WINDOW = 2018278  # error_subcode: sent outside the 24 h window

router = APIRouter()


class SendError(Exception):
    """A send that may work later (Meta busy, rate limit, network): the job is retried."""


def connect_page(conn, fernet_key, tenant_id, *, page_id, app_id, app_secret, page_token) -> int:
    """Connect (or reconnect) a company's Facebook Page. The app secret and the Page token are
    stored encrypted. Returns the channel id."""
    values = {
        "page_id": page_id,
        "app_id": app_id,
        "app_secret": app_secret,
        "page_token": page_token,
    }
    problems = [name for name, value in values.items() if not isinstance(value, str) or not value]
    problems += [n for n in ("page_id", "app_id") if n not in problems and not values[n].isdigit()]
    if problems:
        raise ValueError("missing or invalid: " + ", ".join(problems))
    secret = json.dumps({"app_id": app_id, "app_secret": app_secret, "page_token": page_token})
    row = conn.execute(
        "INSERT INTO channels (tenant_id, type, external_id, secret_enc)"
        " VALUES (%s, 'messenger', %s, %s)"
        " ON CONFLICT (type, external_id) DO UPDATE"
        " SET secret_enc = EXCLUDED.secret_enc, active = true"
        " WHERE channels.tenant_id = EXCLUDED.tenant_id RETURNING id",
        (tenant_id, page_id, encrypt(fernet_key, secret)),
    ).fetchone()
    if row is None:
        raise ValueError("this Page is connected to another company")
    return row[0]


def _pages(conn, fernet_key, page_ids) -> dict:
    """{page id: (channel id, tenant id, credentials)} for live Messenger channels."""
    rows = conn.execute(
        "SELECT ch.external_id, ch.id, ch.tenant_id, ch.secret_enc FROM channels ch"
        " JOIN tenants t ON t.id = ch.tenant_id"
        " WHERE ch.type = 'messenger' AND ch.active AND t.active AND ch.external_id = ANY(%s)",
        (list(page_ids),),
    ).fetchall()
    return {page: (cid, tid, json.loads(decrypt(fernet_key, enc))) for page, cid, tid, enc in rows}


def _creds(conn, fernet_key, channel_id) -> dict | None:
    row = conn.execute(
        "SELECT secret_enc FROM channels WHERE id = %s AND active", (channel_id,)
    ).fetchone()
    return None if row is None else json.loads(decrypt(fernet_key, row[0]))


# ---------- the webhook ----------


@router.get("/webhooks/meta")
def verify(request: Request):
    params = request.query_params
    token = request.app.state.config.meta_verify_token
    if token and params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == token:
        return Response(params.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


@router.post("/webhooks/meta")
async def receive(request: Request):
    body = await request.body()
    try:
        data = json.loads(body)
    except ValueError:
        return Response(status_code=400)
    if not isinstance(data, dict) or data.get("object") != "page":
        return Response(status_code=200)  # WhatsApp comes with P5.4; nothing else is ours
    signature = request.headers.get("x-hub-signature-256")
    return await run_in_threadpool(_queue, request.app.state, body, data, signature)


def _queue(state, body: bytes, data: dict, signature) -> Response:
    entries = [e for e in data.get("entry") or [] if isinstance(e, dict)]
    with state.pool.connection() as conn:
        pages = _pages(conn, state.config.fernet_key, {str(e.get("id")) for e in entries})
        # One delivery comes from one app: every Page in it must check out with its secret.
        # Not a Page of ours (any more): nothing to check or queue, and 200, or Meta retries.
        secrets = {creds["app_secret"] for _, _, creds in pages.values()}
        if not all(verify_meta_signature(s, body, signature) for s in secrets):
            return Response(status_code=403)
        with conn.transaction():
            for entry in entries:
                page = pages.get(str(entry.get("id")))
                for event in entry.get("messaging") or []:
                    if page and isinstance(event, dict):
                        payload = {"channel": page[0], "tenant": page[1], "event": event}
                        jobs.enqueue(conn, "messenger_event", payload)
    return Response(status_code=200)


# ---------- the worker's jobs ----------


def handlers(engine, fernet_key, http: httpx.Client, *, clock=None) -> dict:
    """The worker's Messenger jobs, wired to an engine and an HTTP client."""
    clock = clock or (lambda: datetime.datetime.now(datetime.UTC))
    return {
        "messenger_event": functools.partial(handle_event, engine, fernet_key, clock),
        "messenger_send": functools.partial(send, engine, fernet_key, http, clock),
    }


def _at(event) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(int(event["timestamp"]) / 1000, datetime.UTC)


def _ad(referral) -> dict | None:
    """What an ad click tells us (F11): which ad, from where, and its headline."""
    if not isinstance(referral, dict):
        return None
    context = referral.get("ads_context_data") or {}
    ad = {
        "ad_id": referral.get("ad_id"),
        "source": referral.get("source"),
        "ref": referral.get("ref"),
        "headline": context.get("ad_title") if isinstance(context, dict) else None,
    }
    return {k: str(v)[:300] for k, v in ad.items() if v} or None


def handle_event(engine, fernet_key, clock, conn, job) -> None:
    channel, tenant, event = job.payload["channel"], job.payload["tenant"], job.payload["event"]
    message, postback = event.get("message") or {}, event.get("postback") or {}
    referral = event.get("referral") or message.get("referral") or postback.get("referral")
    now = clock()
    if message.get("is_echo"):  # sent by the Page: by us, or by a person in the Page inbox
        creds = _creds(conn, fernet_key, channel)
        if creds and str(message.get("app_id")) != creds["app_id"]:  # a person replied: pause
            reply = Inbound(
                tenant,
                channel,
                event["recipient"]["id"],
                _at(event),
                text=message.get("text"),
                media="attachment" if message.get("attachments") else None,
                external_id=message.get("mid"),
            )
            engine.human_replied(conn, reply, now=now)
        return
    user = event["sender"]["id"]
    if postback:
        what = {"payload": postback.get("payload"), "external_id": postback.get("mid")}
    elif (message.get("quick_reply") or {}).get("payload"):
        what = {"payload": message["quick_reply"]["payload"], "external_id": message.get("mid")}
    elif message.get("text"):
        what = {"text": message["text"], "external_id": message.get("mid")}
    elif message.get("attachments"):
        media = message["attachments"][0].get("type") or "attachment"
        what = {"media": media, "external_id": message.get("mid")}
    else:
        if ad := _ad(referral):  # an ad click with nothing to answer yet: remember the ad
            conn.execute(
                "INSERT INTO contacts (tenant_id, channel_id, external_user_id, source_ad)"
                " VALUES (%s, %s, %s, %s) ON CONFLICT (channel_id, external_user_id)"
                " DO UPDATE SET source_ad = coalesce(contacts.source_ad, EXCLUDED.source_ad)",
                (tenant, channel, user, Jsonb(ad)),
            )
        return  # read receipts, deliveries, reactions: nothing to answer
    msg = Inbound(tenant, channel, user, _at(event), source_ad=_ad(referral), **what)
    with conn.transaction():  # the reply and its send job are kept together, or neither
        reply = engine.handle(conn, msg, now=now)
        if reply.text:
            send_job = {"channel": channel, "tenant": tenant, "user": user, "text": reply.text}
            jobs.enqueue(
                conn,
                "messenger_send",
                send_job | {"buttons": list(reply.buttons)},
                max_attempts=SEND_ATTEMPTS,
            )


def _event(conn, tenant, kind, detail) -> None:
    conn.execute(
        "INSERT INTO audit_events (tenant_id, kind, detail) VALUES (%s, %s, %s)",
        (tenant, kind, Jsonb(detail)),
    )


def send(engine, fernet_key, http, clock, conn, job) -> None:
    p = job.payload
    creds = _creds(conn, fernet_key, p["channel"])
    if creds is None:
        return  # disconnected since: nothing to send with
    last = conn.execute(
        "SELECT max(m.created_at) FROM messages m"
        " JOIN conversations cv ON cv.id = m.conversation_id"
        " JOIN contacts c ON c.id = cv.contact_id"
        " WHERE c.channel_id = %s AND c.external_user_id = %s AND m.role = 'student'",
        (p["channel"], p["user"]),
    ).fetchone()[0]
    if last is None or clock() - last > WINDOW:
        _event(conn, p["tenant"], "messenger_window_closed", {"user": p["user"]})
        return  # Meta's rule: no bot messages after 24 h (a person can reply from the inbox)
    message = {"text": p["text"][:MAX_TEXT]}
    labels = button_labels(conn, p["tenant"], p["buttons"][:MAX_QUICK_REPLIES])
    if labels:
        message["quick_replies"] = [
            {"content_type": "text", "title": b["label"], "payload": b["code"]} for b in labels
        ]
    try:
        response = http.post(
            f"{GRAPH}/me/messages",
            json={"recipient": {"id": p["user"]}, "messaging_type": "RESPONSE", "message": message},
            headers={"Authorization": f"Bearer {creds['page_token']}"},
        )
    except httpx.HTTPError as error:  # no connection, timeout: try again later
        raise SendError(f"{type(error).__name__}: {error}") from None
    if response.is_success:
        return
    try:
        error = response.json().get("error") or {}
    except ValueError:
        error = {}
    code, subcode = error.get("code"), error.get("error_subcode")
    if response.status_code >= 500 or code in RETRY_CODES:
        raise SendError(f"Graph API {response.status_code}: {error.get('message', '')}")
    detail = {"user": p["user"], "status": response.status_code, "code": code, "subcode": subcode}
    if code in UNAVAILABLE_CODES:
        _event(conn, p["tenant"], "messenger_user_unavailable", detail)
    elif subcode == OUTSIDE_WINDOW:
        _event(conn, p["tenant"], "messenger_window_closed", detail)
    else:  # an expired token, a lost permission, or a request Meta rejects: the operator acts
        failed = detail | {"message": error.get("message")}
        _event(conn, p["tenant"], "messenger_send_failed", failed)
        engine.notify("alert", {"tenant": p["tenant"], "channel": p["channel"], **detail})
