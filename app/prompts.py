"""Prompt assembly (PRD §9.2, D-019): what one AI call sends, token-lean and cache-friendly.

Layout (render order is system → messages, and the cache is a prefix match):
  system:   pack prompt + knowledge + core rules (byte-identical per tenant and knowledge
            version) with the one cache breakpoint after it
  messages: the last 12 messages of this conversation, then the new student message with a
            <context> block in front. Everything that changes per turn (time, profile) is
            only in that last message, after the cached prefix.
"""

import datetime
import json
import zoneinfo
from dataclasses import dataclass

HISTORY_LIMIT = 12  # the profile carries older facts (D-019)
IDLE_SPLIT = datetime.timedelta(hours=72)  # a longer silence starts a new conversation
MAX_STUDENT_CHARS = 1000
SHORTENED = " …(message shortened)"
MAX_TOKENS = 500  # a customer reply never needs more; a jailbroken one stays useless
TEMPERATURE = 0.2
SAMPLING_MODELS = ("claude-haiku-4-5",)  # models that accept temperature (Sonnet 5 rejects it)


@dataclass(frozen=True)
class Message:
    role: str  # 'student', 'bot', 'staff' or 'system' (as stored)
    content: str
    created_at: datetime.datetime


def compact_json(value) -> str:
    """Tool results and profile: no spaces, sorted keys, Bangla kept as is (fewer tokens)."""
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def shorten(text: str, limit: int = MAX_STUDENT_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + SHORTENED


def recent_history(history: list[Message], now: datetime.datetime) -> list[Message]:
    """The part of the conversation the AI sees: after the last 72-hour silence (also before
    `now`), without internal 'system' rows, at most the last 12 messages."""
    kept: list[Message] = []
    previous = None
    for message in sorted(history, key=lambda m: m.created_at):
        if previous is not None and message.created_at - previous > IDLE_SPLIT:
            kept = []  # a long silence: what came before is an old conversation
        previous = message.created_at
        if message.role != "system":
            kept.append(message)
    if previous is not None and now - previous > IDLE_SPLIT:
        return []
    return kept[-HISTORY_LIMIT:]


def _turn(message: Message) -> dict:
    if message.role == "student":
        return {"role": "user", "content": shorten(message.content)}
    if message.role == "staff":  # the model must know a person replied, not itself
        return {"role": "assistant", "content": "[staff reply] " + message.content}
    return {"role": "assistant", "content": message.content}  # bot, incl. quick answers


def context_block(*, now, timezone, channel, profile, source_ad=None) -> str:
    local = now.astimezone(zoneinfo.ZoneInfo(timezone))
    parts = [
        f"now={local:%Y-%m-%d %H:%M} {timezone} ({local:%a})",
        f"channel={channel}",
        f"profile={compact_json(profile or {})}",
    ]
    if source_ad:
        parts.append(f"source_ad={source_ad}")
    return "<context>" + "; ".join(parts) + "</context>"


def build_request(
    *,
    model: str,
    system_prompt: str,
    history: list[Message],
    student_text: str,
    now: datetime.datetime,
    timezone: str,
    channel: str,
    profile: dict,
    source_ad: str | None = None,
    cache_ttl: str = "5m",
    tools: list | None = None,
) -> dict:
    """Keyword arguments for messages.create()."""
    if now.utcoffset() is None:
        raise TypeError("now must be timezone-aware")
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ValueError("system prompt is empty")
    cache = {"type": "ephemeral"} | ({"ttl": "1h"} if cache_ttl == "1h" else {})
    turns = [_turn(m) for m in recent_history(history, now)]
    while turns and turns[0]["role"] != "user":
        turns.pop(0)  # the API wants the conversation to start with the customer
    context = context_block(
        now=now, timezone=timezone, channel=channel, profile=profile, source_ad=source_ad
    )
    turns.append({"role": "user", "content": context + "\n" + shorten(student_text)})
    request = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": [{"type": "text", "text": system_prompt, "cache_control": cache}],
        "messages": turns,
    }
    if model.startswith(SAMPLING_MODELS):
        request["temperature"] = TEMPERATURE
    if tools:
        request["tools"] = tools
    return request
