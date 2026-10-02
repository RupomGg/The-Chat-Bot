"""The conversation engine (PRD §5, §6.1-6.3, §6.8, D-018, D-019): one incoming message in,
at most one reply out, the same for every channel.

Order of checks: duplicate → store (redacted) → paused by a person → non-text → quick answer
(free, always allowed) → monthly hard cap → off-topic redirect window → daily AI cap →
abuse guard on the input → the AI (with up to 5 tool rounds) → guard on the reply.
Everything for one contact runs under a lock on that contact, so two messages from the same
person are handled one after the other, in order.
"""

import datetime
import functools
import logging
import time
import zoneinfo
from dataclasses import dataclass, field
from decimal import Decimal

from psycopg.types.json import Jsonb

from app import guard, llm, prompts, tools
from app.knowledge import published_knowledge, render_system_prompt
from app.packs import load_pack
from app.quick_answers import find_quick_answer
from app.redact import redact

log = logging.getLogger("app.engine")

NEW_CONVERSATION_AFTER = prompts.IDLE_SPLIT  # 72 hours
MAX_TOOL_ROUNDS = 5
OFF_TOPIC_LIMIT = 3  # declined requests in a row before the AI is switched off for a while
REDIRECT_FOR = datetime.timedelta(hours=1)
UNANSWERED_LIMIT = 2  # unanswered questions in a row before a person takes over
REDIRECT_BUTTONS = 3
BANGLA = (chr(0x0980), chr(0x09FF))  # the Bengali Unicode block
MEDIA_REPLY = (
    "Sorry, I can only read text messages. Please type your question. / "
    "দুঃখিত, আমি শুধু লেখা পড়তে পারি। অনুগ্রহ করে প্রশ্নটি লিখে পাঠান।"
)
LOG_SOURCE = {"quick": "quick", "llm": "llm", "handoff": "handoff"}  # others: 'fallback'


@dataclass(frozen=True)
class Inbound:
    """One message from a channel adapter (Level 5)."""

    tenant_id: int
    channel_id: int
    external_user_id: str
    received_at: datetime.datetime
    text: str | None = None
    payload: str | None = None  # a button tap
    media: str | None = None  # 'image', 'voice', 'sticker', … (no text)
    external_id: str | None = None  # the channel's message id, for duplicates
    source_ad: dict | None = None


@dataclass(frozen=True)
class Reply:
    text: str | None  # None: stay silent
    source: str  # quick, llm, fallback, handoff, redirect, media, silent, duplicate
    buttons: tuple = ()
    effects: tuple = ()


@dataclass
class Turn:
    """What the AI calls of one reply cost and did, for the performance log."""

    model: str
    usage: list = field(default_factory=list)
    cost: Decimal = Decimal(0)
    tools: list = field(default_factory=list)
    stop_reason: str | None = None
    error: str | None = None
    llm_ms: int = 0


def _notify_log(kind: str, detail: dict) -> None:
    log.info("notify %s %s", kind, detail)


@functools.cache
def _pack(name: str):
    return load_pack(name)


class Engine:
    def __init__(self, clients: dict, *, notify=_notify_log):
        """clients: {"claude": Anthropic client, "gemini": Gemini client}; notify(kind, detail)
        tells people about hot leads, handoffs and alerts."""
        self.clients = clients
        self.notify = notify

    def handle(self, conn, msg: Inbound, *, now: datetime.datetime) -> Reply:
        with conn.transaction():
            tenant = self._tenant(conn, msg.tenant_id)
            contact = self._contact(conn, msg)  # locked until the transaction ends
            conversation = self._conversation(conn, tenant, contact, now)
            if msg.external_id and self._seen(conn, contact["id"], msg.external_id):
                return Reply(None, "duplicate")
            text = self._store_student(conn, tenant, conversation, msg)
            reply, turn = self._decide(conn, tenant, contact, conversation, msg, text, now)
            if reply.text is not None:
                self._store_bot(conn, tenant, conversation, reply, turn, msg, now)
            return reply

    # ---------- loading ----------

    def _tenant(self, conn, tenant_id) -> dict:
        row = conn.execute(
            "SELECT id, name, industry, timezone, country_code, model, cache_ttl, fallback_text,"
            " settings, hard_cap, bot_pause_hours, daily_ai_reply_cap"
            " FROM tenants WHERE id = %s AND active",
            (tenant_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"no active tenant {tenant_id}")
        keys = "id name industry timezone country model cache_ttl fallback settings"
        keys += " hard_cap pause_hours daily_cap"
        tenant = dict(zip(keys.split(), row, strict=True))
        tenant["pack"] = _pack(tenant["industry"])
        tenant["zone"] = zoneinfo.ZoneInfo(tenant["timezone"])
        return tenant

    def _contact(self, conn, msg: Inbound) -> dict:
        conn.execute(
            "INSERT INTO contacts (tenant_id, channel_id, external_user_id, source_ad)"
            " VALUES (%s, %s, %s, %s) ON CONFLICT (channel_id, external_user_id) DO NOTHING",
            (
                msg.tenant_id,
                msg.channel_id,
                msg.external_user_id,
                Jsonb(msg.source_ad) if msg.source_ad else None,
            ),
        )
        row = conn.execute(
            "SELECT c.id, c.name, c.phone, c.email, c.adult, c.profile, c.source_ad, ch.type"
            " FROM contacts c JOIN channels ch ON ch.id = c.channel_id"
            " WHERE c.tenant_id = %s AND c.channel_id = %s AND c.external_user_id = %s"
            " FOR UPDATE OF c",
            (msg.tenant_id, msg.channel_id, msg.external_user_id),
        ).fetchone()
        return dict(
            zip(
                ["id", "name", "phone", "email", "adult", "profile", "source_ad", "channel"],
                row,
                strict=True,
            )
        )

    def _conversation(self, conn, tenant, contact, now) -> dict:
        row = conn.execute(
            "SELECT id, state, paused_until, unanswered_streak, off_topic_streak,"
            " redirect_until, last_message_at FROM conversations"
            " WHERE tenant_id = %s AND contact_id = %s ORDER BY id DESC LIMIT 1",
            (tenant["id"], contact["id"]),
        ).fetchone()
        if row is None or row[1] == "closed" or now - row[6] > NEW_CONVERSATION_AFTER:
            row = conn.execute(
                "INSERT INTO conversations (tenant_id, contact_id, last_message_at, created_at)"
                " VALUES (%s, %s, %s, %s) RETURNING id, state, paused_until,"
                " unanswered_streak, off_topic_streak, redirect_until, last_message_at",
                (tenant["id"], contact["id"], now, now),
            ).fetchone()
        else:
            conn.execute(
                "UPDATE conversations SET last_message_at = %s WHERE id = %s", (now, row[0])
            )
        keys = ["id", "state", "paused_until", "unanswered", "off_topic", "redirect_until", "last"]
        return dict(zip(keys, row, strict=True))

    def _seen(self, conn, contact_id, external_id) -> bool:
        row = conn.execute(
            "SELECT 1 FROM messages m JOIN conversations c ON c.id = m.conversation_id"
            " WHERE c.contact_id = %s AND m.external_id = %s AND m.role = 'student'",
            (contact_id, external_id),
        ).fetchone()
        return row is not None

    def _store_student(self, conn, tenant, conversation, msg: Inbound) -> str:
        if msg.media:
            content = f"[{msg.media}]"
        elif msg.payload and not msg.text:
            content = f"[button {msg.payload}]"
        else:
            content = redact(msg.text or "").strip() or "[empty]"
        conn.execute(
            "INSERT INTO messages (tenant_id, conversation_id, role, content, external_id,"
            " created_at) VALUES (%s, %s, 'student', %s, %s, %s)",
            (tenant["id"], conversation["id"], content, msg.external_id, msg.received_at),
        )
        return content

    # ---------- deciding the reply ----------

    def _decide(self, conn, tenant, contact, conversation, msg, text, now) -> tuple:
        if conversation["state"] == "human":
            if conversation["paused_until"] and conversation["paused_until"] > now:
                return Reply(None, "silent"), None  # a person is handling it
            conn.execute(
                "UPDATE conversations SET state = 'bot', paused_until = NULL WHERE id = %s",
                (conversation["id"],),
            )
        if msg.media:
            return Reply(MEDIA_REPLY, "media"), None

        quick = self._quick(conn, tenant, msg, text)
        if quick is not None and quick.text:
            return Reply(quick.text, "quick", buttons=quick.buttons), None
        if quick is not None:  # an action-only quick answer: let the AI start it
            text = "(tapped: I want to book an appointment)"

        if self._over_hard_cap(conn, tenant, conversation, now):
            return Reply(tenant["fallback"], "fallback"), None
        if conversation["redirect_until"] and conversation["redirect_until"] > now:
            return self._redirect(conn, tenant), None
        midnight = now.astimezone(tenant["zone"]).replace(hour=0, minute=0, second=0, microsecond=0)
        if self._ai_replies_today(conn, contact, midnight) >= tenant["daily_cap"]:
            # No AI until tomorrow; the bot isn't paused, so quick answers still work.
            if not self._event_since(conn, conversation, "daily_cap", midnight):
                self._event(
                    conn, tenant, conversation, now, "daily_cap", {"cap": tenant["daily_cap"]}
                )
                self.notify("handoff", {"tenant": tenant["id"], "conversation": conversation["id"]})
            staff = tenant["pack"].terms["staff"]["en"].lower()
            text = f"A {staff} will continue this conversation here soon."
            return Reply(text, "handoff"), None

        blocked = guard.check_input(text)
        if blocked:
            self._event(conn, tenant, conversation, now, "input_blocked", {"reason": blocked})
            self._count_off_topic(conn, conversation, now)
            return self._redirect(conn, tenant), None

        return self._ai_turn(conn, tenant, contact, conversation, text, now)

    def _quick(self, conn, tenant, msg, text):
        language = "bn" if any(BANGLA[0] <= ch <= BANGLA[1] for ch in text) else "en"
        if msg.payload:
            return find_quick_answer(conn, tenant["id"], payload=msg.payload, language=language)
        return find_quick_answer(conn, tenant["id"], text=text, language=language)

    def _over_hard_cap(self, conn, tenant, conversation, now) -> bool:
        month_start = now.astimezone(tenant["zone"]).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        position = conn.execute(
            "SELECT count(*) FROM conversations WHERE tenant_id = %s AND created_at >= %s"
            " AND id <= %s",
            (tenant["id"], month_start, conversation["id"]),
        ).fetchone()[0]
        if position <= tenant["hard_cap"]:
            return False
        already = conn.execute(
            "SELECT 1 FROM audit_events WHERE tenant_id = %s AND kind = 'hard_cap'"
            " AND created_at >= %s",
            (tenant["id"], month_start),
        ).fetchone()
        if already is None:  # alert once a month, not on every message
            self._event(conn, tenant, conversation, now, "hard_cap", {"cap": tenant["hard_cap"]})
            self.notify("alert", {"tenant": tenant["id"], "reason": "hard_cap"})
        return True

    def _ai_replies_today(self, conn, contact, midnight) -> int:
        """AI replies to this contact since midnight in the company's timezone."""
        return conn.execute(
            "SELECT count(*) FROM bot_turns t JOIN conversations c ON c.id = t.conversation_id"
            " WHERE c.contact_id = %s AND t.source = 'llm' AND t.created_at >= %s",
            (contact["id"], midnight),
        ).fetchone()[0]

    def _event_since(self, conn, conversation, kind, since) -> bool:
        row = conn.execute(
            "SELECT 1 FROM audit_events WHERE conversation_id = %s AND kind = %s"
            " AND created_at >= %s",
            (conversation["id"], kind, since),
        ).fetchone()
        return row is not None

    def _redirect(self, conn, tenant) -> Reply:
        rows = conn.execute(
            "SELECT code FROM quick_answers WHERE tenant_id = %s AND active ORDER BY id LIMIT %s",
            (tenant["id"], REDIRECT_BUTTONS),
        ).fetchall()
        text = f"I can only help with {tenant['name']}'s services. What would you like to know?"
        return Reply(text, "redirect", buttons=tuple(code for (code,) in rows))

    def _count_off_topic(self, conn, conversation, now) -> None:
        streak = conn.execute(
            "UPDATE conversations SET off_topic_streak = off_topic_streak + 1 WHERE id = %s"
            " RETURNING off_topic_streak",
            (conversation["id"],),
        ).fetchone()[0]
        if streak >= OFF_TOPIC_LIMIT:
            conn.execute(
                "UPDATE conversations SET redirect_until = %s, off_topic_streak = 0 WHERE id = %s",
                (now + REDIRECT_FOR, conversation["id"]),
            )

    # ---------- the AI turn ----------

    def _ai_turn(self, conn, tenant, contact, conversation, text, now) -> tuple:
        turn = Turn(model=tenant["model"])
        knowledge = published_knowledge(conn, tenant["id"])
        if knowledge is None:  # nothing to answer from yet: a person answers
            return self._fallback(conn, tenant, conversation, now, "no knowledge published"), None
        pack = tenant["pack"]
        request = prompts.build_request(
            model=tenant["model"],
            system_prompt=render_system_prompt(pack, tenant["name"], knowledge),
            history=self._history(conn, conversation),
            student_text=text,
            now=now,
            timezone=tenant["timezone"],
            channel=contact["channel"],
            profile=self._profile(contact),
            source_ad=(contact["source_ad"] or {}).get("id"),
            cache_ttl=tenant["cache_ttl"],
            tools=tools.schemas(pack),
        )
        ctx = tools.ToolContext(
            conn=conn,
            tenant_id=tenant["id"],
            contact_id=contact["id"],
            conversation_id=conversation["id"],
            pack=pack,
            settings=tenant["settings"],
            now=now,
            timezone=tenant["timezone"],
            country=tenant["country"],
            pause_hours=tenant["pause_hours"],
        )
        provider = "gemini" if tenant["model"].startswith("gemini-") else "claude"
        if provider not in self.clients:  # no key set for this company's AI: tell the operator
            turn.error = f"no {provider} key"
            outcome = llm.Outcome("fallback", action="alert", error=turn.error)
            return self._finish(conn, tenant, contact, conversation, outcome, [], now), turn
        client = self.clients[provider]
        effects = []
        for _ in range(MAX_TOOL_ROUNDS + 1):
            started = time.monotonic()
            outcome = llm.call(client, request)
            turn.llm_ms += int((time.monotonic() - started) * 1000)
            turn.usage.append(outcome.usage)
            turn.cost += outcome.cost_usd
            turn.stop_reason = outcome.stop_reason
            if outcome.kind != "tool_use":
                break
            results = []
            for call in outcome.tool_calls:
                result = tools.run(ctx, call)
                turn.tools.append(call.name)
                effects.extend(result.effects)
                results.append(tools.result_block(call, result))
            request["messages"] += [
                {"role": "assistant", "content": list(outcome.content)},
                {"role": "user", "content": results},
            ]
        else:  # still asking for tools after 5 rounds
            outcome = llm.Outcome("fallback", action="event", error="too many tool rounds")
        turn.error = outcome.error
        return self._finish(conn, tenant, contact, conversation, outcome, effects, now), turn

    def _history(self, conn, conversation) -> list:
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE conversation_id = %s"
            " ORDER BY created_at, id",
            (conversation["id"],),
        ).fetchall()
        return [prompts.Message(*row) for row in rows[:-1]]  # the last one is this message

    def _profile(self, contact) -> dict:
        known = {
            k: contact[k] for k in ("name", "phone", "email", "adult") if contact[k] is not None
        }
        return contact["profile"] | known

    def _finish(self, conn, tenant, contact, conversation, outcome, effects, now) -> Reply:
        if outcome.kind != "reply":
            if outcome.action == "alert":
                self.notify("alert", {"tenant": tenant["id"], "error": outcome.error})
            return self._fallback(conn, tenant, conversation, now, outcome.error or "fallback")

        text = outcome.text
        blocked = guard.check_reply(text)
        if blocked == "code":  # the AI slipped: the customer never sees it
            self._event(conn, tenant, conversation, now, "off_topic_blocked", {"reason": blocked})
            effects.append("off_topic")
            text = self._redirect(conn, tenant).text
        elif blocked:  # too long for the channel
            return self._fallback(conn, tenant, conversation, now, f"reply {blocked}")

        if "off_topic" in effects:
            self._count_off_topic(conn, conversation, now)
        else:
            conn.execute(
                "UPDATE conversations SET off_topic_streak = 0 WHERE id = %s", (conversation["id"],)
            )
        if "unanswered" in effects:
            streak = conn.execute(
                "SELECT unanswered_streak FROM conversations WHERE id = %s", (conversation["id"],)
            ).fetchone()[0]
            if streak >= UNANSWERED_LIMIT and "handoff" not in effects:
                self._handoff(conn, tenant, conversation, now, "unanswered", "2 in a row")
                effects.append("handoff")
        else:
            conn.execute(
                "UPDATE conversations SET unanswered_streak = 0 WHERE id = %s",
                (conversation["id"],),
            )
        if "became_hot" in effects:
            self.notify("hot_lead", {"tenant": tenant["id"], "contact": contact["id"]})
        if "handoff" in effects:
            self.notify("handoff", {"tenant": tenant["id"], "conversation": conversation["id"]})
        return Reply(text, "llm", effects=tuple(effects))

    def _fallback(self, conn, tenant, conversation, now, why: str) -> Reply:
        """The AI couldn't answer: the company's fallback text, and a person takes over."""
        self._handoff(conn, tenant, conversation, now, "unanswered", why)
        self.notify("handoff", {"tenant": tenant["id"], "conversation": conversation["id"]})
        return Reply(tenant["fallback"], "fallback", effects=("handoff",))

    def _handoff(self, conn, tenant, conversation, now, reason, summary) -> None:
        conn.execute(
            "UPDATE conversations SET state = 'human', paused_until = %s WHERE id = %s",
            (now + datetime.timedelta(hours=tenant["pause_hours"]), conversation["id"]),
        )
        self._event(
            conn, tenant, conversation, now, "handoff", {"reason": reason, "summary": summary}
        )

    def _event(self, conn, tenant, conversation, now, kind, detail) -> None:
        """An audit event at the engine's clock (the same clock the limits are counted by)."""
        conn.execute(
            "INSERT INTO audit_events (tenant_id, conversation_id, kind, detail, created_at)"
            " VALUES (%s, %s, %s, %s, %s)",
            (tenant["id"], conversation["id"], kind, Jsonb(detail), now),
        )

    # ---------- storing the reply ----------

    def _store_bot(self, conn, tenant, conversation, reply, turn, msg, now) -> None:
        message_id = conn.execute(
            "INSERT INTO messages (tenant_id, conversation_id, role, content, created_at)"
            " VALUES (%s, %s, 'bot', %s, %s) RETURNING id",
            (tenant["id"], conversation["id"], reply.text, now),
        ).fetchone()[0]
        usage = turn.usage if turn else []
        error = (turn.error or "")[:100] if turn else ""
        conn.execute(
            "INSERT INTO bot_turns (tenant_id, conversation_id, message_id, received_at, source,"
            " channel, model, latency_ms, llm_ms, input_tokens, cache_read_tokens,"
            " cache_write_tokens, output_tokens, cost_usd, tool_calls, stop_reason, error_code,"
            " created_at)"
            " SELECT %s, %s, %s, %s, %s, ch.type, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s"
            " FROM channels ch WHERE ch.id = %s",
            (
                tenant["id"],
                conversation["id"],
                message_id,
                msg.received_at,
                "llm"
                if turn and reply.source == "llm"
                else LOG_SOURCE.get(reply.source, "fallback"),
                turn.model if turn else None,
                max(0, int((now - msg.received_at).total_seconds() * 1000)),
                turn.llm_ms if turn else None,
                sum(u.input for u in usage) if turn else None,
                sum(u.cache_read for u in usage) if turn else None,
                sum(u.cache_write for u in usage) if turn else None,
                sum(u.output for u in usage) if turn else None,
                turn.cost if turn else Decimal(0),
                turn.tools if turn else [],
                turn.stop_reason if turn else None,
                error or None,
                now,
                msg.channel_id,
            ),
        )
