"""Prompt assembly (P4.1, PRD §9.2, D-019)."""

import datetime
import json

import pytest

from app.knowledge import render_system_prompt
from app.packs import load_pack
from app.prompts import (
    HISTORY_LIMIT,
    MAX_STUDENT_CHARS,
    SHORTENED,
    Message,
    build_request,
    compact_json,
    recent_history,
)

UTC = datetime.UTC
NOW = datetime.datetime(2026, 9, 23, 15, 14, tzinfo=UTC)  # 21:14 in Dhaka, a Wednesday
SYSTEM = render_system_prompt(load_pack("study_abroad"), "Acme Consultancy", "Fees: ৳5,000.")


def ago(**delta):
    return NOW - datetime.timedelta(**delta)


def build(**overrides):
    args = {
        "model": "claude-haiku-4-5",
        "system_prompt": SYSTEM,
        "history": [],
        "student_text": "UK fees koto?",
        "now": NOW,
        "timezone": "Asia/Dhaka",
        "channel": "messenger",
        "profile": {"intake": "2027-01", "name": "রহিম"},
    }
    return build_request(**(args | overrides))


# ---------- the cached system part ----------


def test_system_part_is_byte_identical_across_turns():
    first = build(student_text="hi", now=NOW, profile={})
    later = build(
        student_text="fees?",
        now=NOW + datetime.timedelta(hours=5),
        profile={"phone": "+8801712345678"},
        history=[Message("student", "hi", ago(minutes=1))],
    )
    assert json.dumps(first["system"]) == json.dumps(later["system"])


def test_system_part_changes_when_knowledge_changes():
    other = render_system_prompt(load_pack("study_abroad"), "Acme Consultancy", "Fees: ৳6,000.")
    assert build()["system"] != build(system_prompt=other)["system"]


def test_one_cache_breakpoint_after_the_system_part():
    system = build()["system"]
    assert system == [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
    assert build(cache_ttl="1h")["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "cache_control" not in json.dumps(build()["messages"])  # only one breakpoint


def test_nothing_that_changes_per_turn_is_in_the_system_part():
    system = build()["system"][0]["text"]
    # The instructions may *mention* the <context> block; its values must never be here.
    for per_turn in ("2026-09-23", "21:14", "channel=messenger", "রহিম", "<context>now="):
        assert per_turn not in system


# ---------- the context block ----------


def test_context_block_uses_the_company_timezone_and_sorted_profile():
    last = build(source_ad="uk-ielts-oct")["messages"][-1]
    assert last == {
        "role": "user",
        "content": "<context>now=2026-09-23 21:14 Asia/Dhaka (Wed); channel=messenger; "
        'profile={"intake":"2027-01","name":"রহিম"}; source_ad=uk-ielts-oct</context>'
        + chr(10)
        + "UK fees koto?",
    }


def test_context_block_for_another_timezone_and_no_ad():
    content = build(timezone="Europe/London", profile=None)["messages"][-1]["content"]
    assert content.startswith("<context>now=2026-09-23 16:14 Europe/London (Wed); ")
    assert "profile={}" in content and "source_ad" not in content


def test_profile_json_is_the_same_whatever_the_key_order():
    a = build(profile={"b": 1, "a": 2})["messages"][-1]["content"]
    b = build(profile={"a": 2, "b": 1})["messages"][-1]["content"]
    assert a == b


# ---------- history ----------


def conversation(n, start_minutes_ago=100):
    roles = ["student", "bot"]
    return [Message(roles[i % 2], f"m{i}", ago(minutes=start_minutes_ago - i)) for i in range(n)]


def test_empty_history_is_just_the_new_message():
    messages = build()["messages"]
    assert len(messages) == 1 and messages[0]["role"] == "user"


def test_history_is_limited_to_the_last_12():
    kept = recent_history(conversation(20), NOW)
    assert len(kept) == HISTORY_LIMIT
    assert [m.content for m in kept] == [f"m{i}" for i in range(8, 20)]


def test_the_ai_sees_the_last_12_and_starts_with_the_customer():
    messages = build(history=conversation(21))["messages"]  # 21 → last 12 → m9 (bot) first
    assert messages[0] == {"role": "user", "content": "m10"}
    assert messages[-2] == {"role": "user", "content": "m20"}
    assert len(messages) == 12  # m10..m20 (11 turns) + the new message


def test_only_messages_after_a_72_hour_silence_count():
    old = [
        Message("student", "old question", ago(days=5)),
        Message("bot", "old answer", ago(days=5)),
    ]
    new = [Message("student", "new question", ago(hours=1))]
    assert [m.content for m in recent_history(old + new, NOW)] == ["new question"]


def test_exactly_72_hours_is_still_the_same_conversation():
    history = [
        Message("student", "a", ago(hours=73)),
        Message("bot", "b", ago(hours=1)),  # 72 hours after "a": same conversation
    ]
    assert [m.content for m in recent_history(history, NOW)] == ["a", "b"]


def test_everything_older_than_72_hours_is_forgotten():
    history = [
        Message("student", "hi", ago(hours=73)),
        Message("bot", "hello", ago(hours=72, minutes=1)),
    ]
    assert recent_history(history, NOW) == []
    assert len(build(history=history)["messages"]) == 1


def test_history_order_comes_from_the_timestamps():
    history = [
        Message("bot", "second", ago(minutes=1)),
        Message("student", "first", ago(minutes=2)),
    ]
    assert [m["content"] for m in build(history=history)["messages"][:2]] == ["first", "second"]


def test_staff_quick_answer_and_system_rows():
    history = [
        Message("student", "fees?", ago(minutes=5)),
        Message("bot", "Counselling is free.", ago(minutes=5)),  # a quick answer
        Message("system", "handoff started", ago(minutes=4)),  # internal: never sent
        Message("staff", "Hi, I'm Nadia from Acme.", ago(minutes=3)),
    ]
    messages = build(history=history)["messages"]
    assert messages[:3] == [
        {"role": "user", "content": "fees?"},
        {"role": "assistant", "content": "Counselling is free."},
        {"role": "assistant", "content": "[staff reply] Hi, I'm Nadia from Acme."},
    ]
    assert "handoff started" not in json.dumps(messages)


def test_history_starting_with_the_bot_is_trimmed():
    history = [Message("bot", "Welcome!", ago(minutes=3))]
    assert build(history=history)["messages"][0]["role"] == "user"


# ---------- sizes ----------


def test_long_student_message_is_capped_before_the_prompt():
    content = build(student_text="x" * 5000)["messages"][-1]["content"]
    student_part = content.split(chr(10), 1)[1]  # after the context block
    assert student_part == "x" * MAX_STUDENT_CHARS + SHORTENED


def test_long_messages_in_history_are_capped_too():
    history = [Message("student", "y" * 3000, ago(minutes=1))]
    assert build(history=history)["messages"][0]["content"] == "y" * MAX_STUDENT_CHARS + SHORTENED


def test_a_message_exactly_at_the_limit_is_kept_whole():
    assert build(student_text="z" * MAX_STUDENT_CHARS)["messages"][-1]["content"].endswith(
        chr(10) + "z" * MAX_STUDENT_CHARS
    )


def test_compact_json_for_tool_results():
    assert compact_json({"b": 1, "a": [1, 2], "n": "রহিম"}) == '{"a":[1,2],"b":1,"n":"রহিম"}'


# ---------- model settings ----------


def test_haiku_gets_a_low_temperature_and_short_replies():
    request = build(model="claude-haiku-4-5")
    assert (request["max_tokens"], request["temperature"]) == (500, 0.2)


@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-opus-5"])
def test_models_that_reject_temperature_dont_get_it(model):
    assert "temperature" not in build(model=model)


def test_tools_only_when_given():
    assert "tools" not in build()
    tools = [{"name": "list_slots", "input_schema": {"type": "object"}}]
    assert build(tools=tools)["tools"] == tools


# ---------- inputs ----------


def test_now_must_be_timezone_aware():
    with pytest.raises(TypeError):
        build(now=NOW.replace(tzinfo=None))


@pytest.mark.parametrize("system", ["", "   ", None])
def test_empty_system_prompt_is_refused(system):
    with pytest.raises(ValueError, match="system prompt is empty"):
        build(system_prompt=system)
