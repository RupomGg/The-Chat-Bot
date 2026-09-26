"""One AI call (PRD §9.1-9.2, D-019, D-021): send the request from app/prompts.py to Claude or
Gemini, turn every possible result into one clear outcome, and price it exactly.

Outcomes: "reply" (text to send), "tool_use" (the engine runs the tools and calls again) or
"fallback" (the engine sends the company's fallback text). A fallback says what else to do:
"event" (log it), "handoff" (a person takes over) or "alert" (tell the operator: a bug or a bad
key, not the weather). The SDKs retry rate limits, overload, 5xx and network errors themselves.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

import anthropic
import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

# USD per million tokens (input, output), from the providers' price lists (checked 2026-09-25).
# Gemini's free tier costs nothing; this is what the paid tier would cost, for comparison.
PRICES = {
    "claude-haiku-4-5": (Decimal("1.00"), Decimal("5.00")),
    "claude-sonnet-5": (Decimal("2.00"), Decimal("10.00")),
    "gemini-3.5-flash": (Decimal("1.50"), Decimal("9.00")),
    "gemini-3.5-flash-lite": (Decimal("0.30"), Decimal("2.50")),
}
CACHE_READ = Decimal("0.1")  # × input price (both providers; Gemini's cache has no write cost)
CACHE_WRITE = {"5m": Decimal("1.25"), "1h": Decimal("2")}  # × input price, by cache TTL
MILLION = Decimal(1_000_000)
MICRO_DOLLAR = Decimal("0.000001")
TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2

NOT_RETRIED = (  # the request itself is wrong: retrying can't help, the operator must look
    anthropic.BadRequestError,
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.NotFoundError,
    anthropic.UnprocessableEntityError,
)
GEMINI_SAFETY_STOPS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}


class UnknownModel(ValueError):
    """A model id we can't price or route. Raised when a company is configured, not mid-chat."""


def check_model(model) -> None:
    if model not in PRICES:
        raise UnknownModel(f"unknown model {model!r}: use one of {sorted(PRICES)}")


@dataclass(frozen=True)
class Usage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass(frozen=True)
class Outcome:
    kind: str  # "reply", "tool_use" or "fallback"
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    content: tuple = ()  # the raw response blocks, appended to history for tool rounds
    usage: Usage = field(default_factory=Usage)
    cost_usd: Decimal = Decimal(0)
    stop_reason: str | None = None
    action: str | None = None  # for fallbacks: "event", "handoff" or "alert"
    error: str | None = None


def cost(model: str, usage: Usage, cache_ttl: str = "5m") -> Decimal:
    """Exact cost in USD (to the millionth), cached reads and writes included."""
    price_in, price_out = PRICES[model]
    total = (
        usage.input * price_in
        + usage.cache_read * price_in * CACHE_READ
        + usage.cache_write * price_in * CACHE_WRITE[cache_ttl]
        + usage.output * price_out
    )
    return (total / MILLION).quantize(MICRO_DOLLAR, rounding=ROUND_HALF_UP)


def make_client(api_key=None) -> anthropic.Anthropic:
    """The Anthropic client: 30-second timeout, 2 automatic retries (429, 529, 5xx, network)."""
    return anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)


def make_gemini_client(api_key) -> genai.Client:
    """The Gemini client: 30-second timeout, 3 tries in all (as for Claude)."""
    options = genai_types.HttpOptions(
        timeout=int(TIMEOUT_SECONDS * 1000),  # milliseconds in this SDK
        retry_options=genai_types.HttpRetryOptions(attempts=MAX_RETRIES + 1),
    )
    return genai.Client(api_key=api_key, http_options=options)


# ---------- Claude ----------


def _usage(response) -> Usage:
    u = response.usage
    return Usage(
        input=u.input_tokens or 0,
        output=u.output_tokens or 0,
        cache_read=getattr(u, "cache_read_input_tokens", None) or 0,
        cache_write=getattr(u, "cache_creation_input_tokens", None) or 0,
    )


def _cache_ttl(request: dict) -> str:
    return request["system"][0].get("cache_control", {}).get("ttl", "5m")


def _call_claude(client, request: dict) -> Outcome:
    model = request["model"]
    try:
        response = client.messages.create(**request)
    except NOT_RETRIED as error:
        return Outcome("fallback", action="alert", error=f"{type(error).__name__}: {error}")
    except anthropic.APIError as error:  # 429, 529, 5xx, timeout, connection: retried already
        return Outcome("fallback", action="event", error=f"{type(error).__name__}: {error}")

    usage = _usage(response)
    spent = cost(model, usage, _cache_ttl(request))
    blocks = tuple(response.content)
    text = "".join(b.text for b in blocks if b.type == "text").strip()
    tools = tuple(ToolCall(b.id, b.name, b.input) for b in blocks if b.type == "tool_use")
    common = {"usage": usage, "cost_usd": spent, "stop_reason": response.stop_reason}

    if response.stop_reason == "tool_use" and tools:
        return Outcome("tool_use", text=text, tool_calls=tools, content=blocks, **common)
    if response.stop_reason == "refusal":
        return Outcome("fallback", action="handoff", error="the model refused", **common)
    if response.stop_reason == "max_tokens":
        return Outcome("fallback", action="event", error="reply cut off at max_tokens", **common)
    if not text:
        return Outcome("fallback", action="event", error="reply had no text", **common)
    return Outcome("reply", text=text, content=blocks, **common)


# ---------- Gemini ----------


def _gemini_config(request: dict) -> genai_types.GenerateContentConfig:
    declarations = [
        genai_types.FunctionDeclaration(
            name=t["name"],
            description=t.get("description", ""),
            parameters_json_schema=t["input_schema"],
        )
        for t in request.get("tools") or ()
    ]
    return genai_types.GenerateContentConfig(
        system_instruction=request["system"][0]["text"],
        max_output_tokens=request["max_tokens"],
        # Thinking tokens count against max_output_tokens: keep them minimal for chat.
        thinking_config=genai_types.ThinkingConfig(
            thinking_level=genai_types.ThinkingLevel.MINIMAL
        ),
        # Only return the calls; our engine runs the tools, never the SDK.
        automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        tools=[genai_types.Tool(function_declarations=declarations)] if declarations else None,
    )


def _gemini_contents(request: dict) -> list:
    contents = []
    for message in request["messages"]:
        if not isinstance(message["content"], str):
            raise NotImplementedError("Gemini tool rounds arrive with the tools (P4.3)")
        role = "user" if message["role"] == "user" else "model"
        contents.append(
            genai_types.Content(role=role, parts=[genai_types.Part(text=message["content"])])
        )
    return contents


def _gemini_usage(response) -> Usage:
    u = response.usage_metadata
    if u is None:
        return Usage()
    cached = u.cached_content_token_count or 0
    return Usage(
        input=(u.prompt_token_count or 0) - cached,  # the prompt count includes cached tokens
        output=(u.candidates_token_count or 0) + (u.thoughts_token_count or 0),  # both billed
        cache_read=cached,
    )


def _call_gemini(client, request: dict) -> Outcome:
    model = request["model"]
    try:
        response = client.models.generate_content(
            model=model, contents=_gemini_contents(request), config=_gemini_config(request)
        )
    except genai_errors.ClientError as error:  # 4xx; 429 is a quota or rate limit, not a bug
        action = "event" if error.code == 429 else "alert"
        return Outcome("fallback", action=action, error=f"{type(error).__name__}: {error}")
    except (genai_errors.ServerError, httpx.HTTPError) as error:  # 5xx, timeout, network
        return Outcome("fallback", action="event", error=f"{type(error).__name__}: {error}")

    usage = _gemini_usage(response)
    common = {"usage": usage, "cost_usd": cost(model, usage)}
    if not response.candidates:
        feedback = response.prompt_feedback
        reason = feedback.block_reason.name if feedback and feedback.block_reason else "none"
        return Outcome("fallback", action="handoff", error=f"prompt blocked: {reason}", **common)
    candidate = response.candidates[0]
    finish = candidate.finish_reason.name if candidate.finish_reason else "STOP"
    common["stop_reason"] = finish.lower()
    parts = candidate.content.parts if candidate.content and candidate.content.parts else []
    text = "".join(p.text for p in parts if p.text and not p.thought).strip()
    calls = tuple(
        ToolCall(
            p.function_call.id or f"call_{i}", p.function_call.name, p.function_call.args or {}
        )
        for i, p in enumerate(parts)
        if p.function_call
    )
    raw = (candidate.content,)
    if calls:
        return Outcome("tool_use", text=text, tool_calls=calls, content=raw, **common)
    if finish in GEMINI_SAFETY_STOPS:
        return Outcome("fallback", action="handoff", error=f"blocked: {finish}", **common)
    if finish == "MAX_TOKENS":
        return Outcome("fallback", action="event", error="reply cut off at max_tokens", **common)
    if finish != "STOP":
        return Outcome("fallback", action="event", error=f"stopped: {finish}", **common)
    if not text:
        return Outcome("fallback", action="event", error="reply had no text", **common)
    return Outcome("reply", text=text, content=raw, **common)


# ---------- entry points ----------


def call(client, request: dict) -> Outcome:
    """Send one request (from prompts.build_request) with the matching client (Anthropic for
    claude-*, Gemini for gemini-*) and classify the result. Never raises for API trouble:
    every failure becomes a fallback with the right action."""
    if request["model"].startswith("gemini-"):
        return _call_gemini(client, request)
    return _call_claude(client, request)


def count_tokens(client, request: dict) -> int:
    """Exact input tokens for a Claude request (replaces the byte estimate, O-013)."""
    fields = ("model", "system", "messages", "tools")
    result = client.messages.count_tokens(**{k: request[k] for k in fields if k in request})
    return result.input_tokens
