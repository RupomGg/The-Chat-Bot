"""One AI call (P4.2, PRD §9.1-9.2, D-019). A fake client: no network, no cost."""

import datetime
import os
from decimal import Decimal
from types import SimpleNamespace

import anthropic
import httpx
import httpx2
import pytest
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app import llm
from app.knowledge import render_system_prompt
from app.llm import Outcome, ToolCall, UnknownModel, Usage, call, check_model, cost, count_tokens
from app.packs import load_pack
from app.prompts import Message, build_request

NOW = datetime.datetime(2026, 9, 25, 9, 30, tzinfo=datetime.UTC)


def request(model="claude-haiku-4-5", cache_ttl="5m", system="You are the assistant."):
    return build_request(
        model=model,
        system_prompt=system,
        history=[],
        student_text="fees?",
        now=NOW,
        timezone="Asia/Dhaka",
        channel="web",
        profile={},
        cache_ttl=cache_ttl,
    )


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def response(blocks, stop="end_turn", usage=None):
    u = usage or {"input_tokens": 100, "output_tokens": 20}
    return SimpleNamespace(content=blocks, stop_reason=stop, usage=SimpleNamespace(**u))


class FakeClient:
    """Records requests; returns a response or raises an error."""

    def __init__(self, result):
        self.result, self.sent = result, []
        self.messages = SimpleNamespace(create=self.create, count_tokens=self.count)

    def create(self, **kwargs):
        self.sent.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def count(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(input_tokens=4321)


REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def status_error(cls, code):
    return cls(f"HTTP {code}", response=httpx2.Response(code, request=REQ), body=None)


# ---------- stop reasons ----------


def test_end_turn_is_a_reply():
    client = FakeClient(response([text("Counselling is free. "), text("Book a session?")]))
    out = call(client, request())
    assert (out.kind, out.text, out.stop_reason, out.action) == (
        "reply",
        "Counselling is free. Book a session?",
        "end_turn",
        None,
    )
    assert client.sent == [request()]  # the request goes out exactly as built


def test_tool_use_returns_the_calls_and_raw_blocks():
    blocks = [text("Let me check."), tool("t1", "list_slots", {"mode": "online"})]
    out = call(FakeClient(response(blocks, stop="tool_use")), request())
    assert out.kind == "tool_use"
    assert out.tool_calls == (ToolCall("t1", "list_slots", {"mode": "online"}),)
    assert out.content == tuple(blocks) and out.text == "Let me check."


def test_tool_use_stop_without_tool_blocks_uses_the_text():
    out = call(FakeClient(response([text("Here you go.")], stop="tool_use")), request())
    assert (out.kind, out.text) == ("reply", "Here you go.")


def test_cut_off_reply_is_a_fallback_event():
    out = call(FakeClient(response([text("The fees are")], stop="max_tokens")), request())
    assert (out.kind, out.action, out.error) == ("fallback", "event", "reply cut off at max_tokens")
    assert out.cost_usd > 0  # the tokens were still spent


def test_refusal_hands_over_to_a_person():
    out = call(FakeClient(response([], stop="refusal")), request())
    assert (out.kind, out.action, out.error) == ("fallback", "handoff", "the model refused")


@pytest.mark.parametrize("blocks", [[], [text("   ")], [tool("t1", "x", {})]])
def test_no_text_is_a_fallback_event(blocks):
    out = call(FakeClient(response(blocks)), request())
    assert (out.kind, out.action, out.error) == ("fallback", "event", "reply had no text")


# ---------- API errors ----------


@pytest.mark.parametrize(
    "error",
    [
        status_error(anthropic.BadRequestError, 400),
        status_error(anthropic.AuthenticationError, 401),
        status_error(anthropic.PermissionDeniedError, 403),
        status_error(anthropic.NotFoundError, 404),
        status_error(anthropic.UnprocessableEntityError, 422),
    ],
)
def test_request_errors_alert_the_operator(error):
    out = call(FakeClient(error), request())
    assert (out.kind, out.action) == ("fallback", "alert")
    assert out.error.startswith(type(error).__name__)
    assert out.cost_usd == 0


@pytest.mark.parametrize(
    "error",
    [
        status_error(anthropic.RateLimitError, 429),
        status_error(anthropic.InternalServerError, 500),
        status_error(anthropic.OverloadedError, 529),
        anthropic.APITimeoutError(request=REQ),
        anthropic.APIConnectionError(request=REQ),
    ],
)
def test_temporary_errors_fall_back_quietly(error):
    out = call(FakeClient(error), request())
    assert (out.kind, out.action) == ("fallback", "event")
    assert out.error.startswith(type(error).__name__)


def test_other_exceptions_are_bugs_and_surface():
    with pytest.raises(ZeroDivisionError):
        call(FakeClient(ZeroDivisionError()), request())


def test_client_retries_temporary_errors_itself():
    client = llm.make_client(api_key="test-key")
    assert (client.max_retries, client.timeout) == (2, 30.0)


# ---------- cost ----------


def test_cost_counts_every_kind_of_token():
    usage = Usage(input=1_000, output=200, cache_read=10_000, cache_write=4_000)
    # Haiku: $1 in, $5 out; reads 0.1×; 5-minute writes 1.25×
    expected = Decimal("0.001") + Decimal("0.001") + Decimal("0.001") + Decimal("0.005")
    assert cost("claude-haiku-4-5", usage) == expected
    # 1-hour writes cost 2×: 4,000 × $1 × 2 / 1M = $0.008 instead of $0.005
    assert cost("claude-haiku-4-5", usage, "1h") == expected + Decimal("0.003")


def test_cost_per_model():
    usage = Usage(input=1_000_000, output=1_000_000)
    assert cost("claude-haiku-4-5", usage) == Decimal("6.000000")
    assert cost("claude-sonnet-5", usage) == Decimal("12.000000")


def test_cost_rounds_to_the_millionth():
    assert cost("claude-haiku-4-5", Usage(input=1)) == Decimal("0.000001")  # 0.000001 exactly
    assert cost("claude-haiku-4-5", Usage(output=1)) == Decimal("0.000005")
    # 5 cached reads × $1 × 0.1 = $0.0000005: exactly half, rounds up
    assert cost("claude-haiku-4-5", Usage(cache_read=5)) == Decimal("0.000001")
    assert cost("claude-haiku-4-5", Usage(cache_read=4)) == Decimal("0.000000")


def test_call_reports_usage_and_cost_including_cache():
    usage = {
        "input_tokens": 50,
        "output_tokens": 100,
        "cache_read_input_tokens": 5_000,
        "cache_creation_input_tokens": 0,
    }
    out = call(FakeClient(response([text("ok")], usage=usage)), request())
    assert out.usage == Usage(input=50, output=100, cache_read=5_000, cache_write=0)
    assert out.cost_usd == Decimal("0.001050")  # 50×1 + 5000×0.1 + 100×5 = 1,050 / 1M


def test_missing_cache_fields_count_as_zero():
    usage = {"input_tokens": 10, "output_tokens": 1, "cache_read_input_tokens": None}
    out = call(FakeClient(response([text("ok")], usage=usage)), request())
    assert out.usage == Usage(input=10, output=1)


def test_one_hour_cache_writes_are_priced_as_such():
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 1_000_000}
    out = call(FakeClient(response([text("ok")], usage=usage)), request(cache_ttl="1h"))
    assert out.cost_usd == Decimal("2.000000")


# ---------- models ----------


@pytest.mark.parametrize(
    "model", ["claude-haiku-4-5", "claude-sonnet-5", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
)
def test_known_models_are_accepted(model):
    check_model(model)


@pytest.mark.parametrize(
    "model",
    [
        "claude-opus-5",
        "gpt-5",
        "claude-haiku-4-5-20251001",
        "gemini-3-flash",  # no price we can bill with: not allowed
        "gemini-2.0-flash",  # shut down by Google
        "",
        None,
        ["claude-haiku-4-5"],
    ],
)
def test_unknown_models_fail_at_configuration(model):
    with pytest.raises((UnknownModel, TypeError)):
        check_model(model)


# ---------- request settings (D-019) ----------


def test_request_settings_reach_the_api():
    client = FakeClient(response([text("ok")]))
    call(client, request())
    sent = client.sent[0]
    assert (sent["max_tokens"], sent["temperature"]) == (500, 0.2)
    call(client, request(model="claude-sonnet-5"))
    assert "temperature" not in client.sent[1]


def test_per_turn_values_never_come_before_the_cache_breakpoint():
    sent = request()
    assert "<context>" not in sent["system"][0]["text"]
    assert sent["messages"][-1]["content"].startswith("<context>")


def test_count_tokens_sends_the_request_without_output_settings():
    client = FakeClient(None)
    tools = [{"name": "list_slots", "input_schema": {"type": "object"}}]
    req = request() | {"tools": tools}
    assert count_tokens(client, req) == 4321
    assert set(client.sent[0]) == {"model", "system", "messages", "tools"}
    count_tokens(client, request())
    assert "tools" not in client.sent[1]


def test_outcome_defaults():
    assert Outcome("reply").usage == Usage() and Outcome("reply").cost_usd == 0


# ---------- the one real call (on demand: pytest -m live -n 0 tests/test_llm.py) ----------


@pytest.mark.live
def test_live_two_turns_hit_the_cache():
    key = os.environ["ANTHROPIC_API_KEY"]  # a KeyError here means: set the key first
    knowledge = "# Demo Consultancy" + chr(10) + ("Office hours Sat-Thu 10:00-19:00. " * 600)
    system = render_system_prompt(load_pack("study_abroad"), "Demo Consultancy", knowledge)
    client = llm.make_client(api_key=key)
    first = request(system=system)
    one = call(client, first)
    history = [Message("student", "fees?", NOW), Message("bot", one.text or "ok", NOW)]
    second = build_request(
        model="claude-haiku-4-5",
        system_prompt=system,
        history=history,
        student_text="office time?",
        now=NOW,
        timezone="Asia/Dhaka",
        channel="web",
        profile={},
    )
    two = call(client, second)
    print("turn 1:", one.kind, one.usage, one.cost_usd)
    print("turn 2:", two.kind, two.usage, two.cost_usd)
    assert two.usage.cache_read > 0


# ---------- Gemini (D-021): same outcomes, real SDK objects, no network ----------

G = genai_types


def g_response(parts=None, finish=G.FinishReason.STOP, usage=None, candidates=True, blocked=None):
    usage = usage or {"prompt_token_count": 120, "candidates_token_count": 30}
    cands = (
        [G.Candidate(content=G.Content(role="model", parts=parts or []), finish_reason=finish)]
        if candidates
        else []
    )
    feedback = G.GenerateContentResponsePromptFeedback(block_reason=blocked) if blocked else None
    return G.GenerateContentResponse(
        candidates=cands,
        prompt_feedback=feedback,
        usage_metadata=G.GenerateContentResponseUsageMetadata(**usage),
    )


class FakeGemini:
    def __init__(self, result):
        self.result, self.sent = result, []
        self.models = SimpleNamespace(generate_content=self.generate)

    def generate(self, **kwargs):
        self.sent.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def gemini_request(**overrides):
    history = [Message("student", "hi", NOW), Message("bot", "Hello!", NOW)]
    args = {
        "model": "gemini-3.5-flash",
        "system_prompt": "You are the assistant.",
        "history": history,
        "student_text": "fees?",
        "now": NOW,
        "timezone": "Asia/Dhaka",
        "channel": "web",
        "profile": {},
    }
    return build_request(**(args | overrides))


def test_gemini_reply():
    client = FakeGemini(g_response([G.Part(text="Counselling "), G.Part(text="is free.")]))
    out = call(client, gemini_request())
    assert (out.kind, out.text, out.stop_reason) == ("reply", "Counselling is free.", "stop")


def test_gemini_request_is_translated():
    client = FakeGemini(g_response([G.Part(text="ok")]))
    call(client, gemini_request())
    sent = client.sent[0]
    assert sent["model"] == "gemini-3.5-flash"
    assert [(c.role, c.parts[0].text[:9]) for c in sent["contents"]] == [
        ("user", "hi"),
        ("model", "Hello!"),
        ("user", "<context>"),
    ]
    config = sent["config"]
    assert config.system_instruction == "You are the assistant."
    assert config.max_output_tokens == 500
    assert config.thinking_config.thinking_level == G.ThinkingLevel.MINIMAL
    assert config.automatic_function_calling.disable is True
    assert config.temperature is None  # Google advises the default for Gemini 3
    assert config.tools is None


def test_gemini_never_goes_to_anthropic_and_claude_never_to_gemini():
    claude, gemini = FakeClient(response([text("x")])), FakeGemini(g_response([G.Part(text="y")]))
    assert call(gemini, gemini_request()).text == "y"
    assert call(claude, request()).text == "x"
    assert claude.sent[0]["model"] == "claude-haiku-4-5"


def test_gemini_tools_are_declared_and_calls_returned():
    tools = [
        {
            "name": "list_slots",
            "description": "Open slots",
            "input_schema": {"type": "object", "properties": {"mode": {"type": "string"}}},
        }
    ]
    call_part = G.Part(
        function_call=G.FunctionCall(id="c1", name="list_slots", args={"mode": "online"})
    )
    nameless = G.Part(function_call=G.FunctionCall(name="list_slots", args=None))
    client = FakeGemini(g_response([G.Part(text="Checking."), call_part, nameless]))
    out = call(client, gemini_request(tools=tools))
    declared = client.sent[0]["config"].tools[0].function_declarations[0]
    assert (declared.name, declared.description) == ("list_slots", "Open slots")
    assert declared.parameters_json_schema == tools[0]["input_schema"]
    assert out.kind == "tool_use" and out.text == "Checking."
    assert out.tool_calls == (
        ToolCall("c1", "list_slots", {"mode": "online"}),
        ToolCall("call_2", "list_slots", {}),
    )
    assert out.content[0].role == "model"  # the raw turn, kept for the next round


def test_gemini_thoughts_are_not_sent_to_the_customer():
    parts = [G.Part(text="let me think...", thought=True), G.Part(text="Fees are 5,000 taka.")]
    assert call(FakeGemini(g_response(parts)), gemini_request()).text == "Fees are 5,000 taka."


@pytest.mark.parametrize(
    "finish, action, error",
    [
        (G.FinishReason.MAX_TOKENS, "event", "reply cut off at max_tokens"),
        (G.FinishReason.SAFETY, "handoff", "blocked: SAFETY"),
        (G.FinishReason.PROHIBITED_CONTENT, "handoff", "blocked: PROHIBITED_CONTENT"),
        (G.FinishReason.RECITATION, "handoff", "blocked: RECITATION"),
        (G.FinishReason.MALFORMED_FUNCTION_CALL, "event", "stopped: MALFORMED_FUNCTION_CALL"),
        (G.FinishReason.OTHER, "event", "stopped: OTHER"),
    ],
)
def test_gemini_stop_reasons(finish, action, error):
    out = call(FakeGemini(g_response([G.Part(text="partial")], finish=finish)), gemini_request())
    assert (out.kind, out.action, out.error) == ("fallback", action, error)


@pytest.mark.parametrize("parts", [[], [G.Part(text="   ")], [G.Part(text="x", thought=True)]])
def test_gemini_no_text_is_a_fallback(parts):
    out = call(FakeGemini(g_response(parts)), gemini_request())
    assert (out.kind, out.error) == ("fallback", "reply had no text")


def test_gemini_missing_finish_reason_and_content_count_as_stop():
    response_ = G.GenerateContentResponse(
        candidates=[G.Candidate(content=None, finish_reason=None)], usage_metadata=None
    )
    out = call(FakeGemini(response_), gemini_request())
    assert (out.kind, out.error, out.stop_reason) == ("fallback", "reply had no text", "stop")
    assert out.usage == Usage() and out.cost_usd == 0


@pytest.mark.parametrize(
    "blocked, reason", [(G.BlockedReason.JAILBREAK, "JAILBREAK"), (None, "none")]
)
def test_gemini_blocked_prompt_hands_over(blocked, reason):
    out = call(FakeGemini(g_response(candidates=False, blocked=blocked)), gemini_request())
    assert (out.kind, out.action, out.error) == ("fallback", "handoff", f"prompt blocked: {reason}")


def g_error(cls, code):
    return cls(code, {"error": {"code": code, "message": "nope", "status": "X"}})


@pytest.mark.parametrize(
    "error, action",
    [
        (g_error(genai_errors.ClientError, 400), "alert"),
        (g_error(genai_errors.ClientError, 403), "alert"),  # bad or restricted key
        (g_error(genai_errors.ClientError, 404), "alert"),  # model gone
        (g_error(genai_errors.ClientError, 429), "event"),  # free-tier quota: not a bug
        (g_error(genai_errors.ServerError, 500), "event"),
        (g_error(genai_errors.ServerError, 503), "event"),
        (httpx.ConnectTimeout("slow"), "event"),
        (httpx.ConnectError("down"), "event"),
    ],
)
def test_gemini_errors(error, action):
    out = call(FakeGemini(error), gemini_request())
    assert (out.kind, out.action) == ("fallback", action)
    assert out.error.startswith(type(error).__name__)


def test_gemini_usage_and_cost_with_cache_and_thinking():
    usage = {
        "prompt_token_count": 10_000,  # includes the 8,000 cached
        "cached_content_token_count": 8_000,
        "candidates_token_count": 100,
        "thoughts_token_count": 20,  # billed as output
    }
    out = call(FakeGemini(g_response([G.Part(text="ok")], usage=usage)), gemini_request())
    assert out.usage == Usage(input=2_000, output=120, cache_read=8_000)
    # 1.50 x 2,000 + 0.15 x 8,000 + 9 x 120 = 3,000 + 1,200 + 1,080 = 5,280 per 1M
    assert out.cost_usd == Decimal("0.005280")


def test_gemini_tool_rounds_wait_for_p4_3():
    req = gemini_request()
    req["messages"].append({"role": "user", "content": [{"type": "tool_result"}]})
    with pytest.raises(NotImplementedError, match="P4.3"):
        call(FakeGemini(g_response([G.Part(text="x")])), req)


def test_gemini_client_settings():
    client = llm.make_gemini_client(api_key="test-key")
    options = client._api_client._http_options
    assert options.timeout == 30_000  # milliseconds
    assert options.retry_options.attempts == 3


@pytest.mark.live
def test_live_gemini_reply():
    key = os.environ["GEMINI_API_KEY"]  # a KeyError here means: set the key first
    system = render_system_prompt(
        load_pack("study_abroad"),
        "Demo Consultancy",
        "Fees: counselling free, processing 5,000 taka.",
    )
    out = call(llm.make_gemini_client(key), gemini_request(system_prompt=system))
    print("gemini:", out.kind, out.stop_reason, out.usage, out.cost_usd, repr(out.text[:200]))
    assert out.kind == "reply", out.error
