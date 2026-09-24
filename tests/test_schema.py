"""Schema rules (migrations/001_init.sql): invalid data must be impossible to store."""

from datetime import UTC, datetime

import psycopg
import pytest
from psycopg import errors, sql

NOW = datetime(2026, 10, 1, 5, 0, tzinfo=UTC)

EXPECTED_TABLES = {
    "schema_version",
    "tenants",
    "knowledge_versions",
    "branches",
    "schedules",
    "holidays",
    "events",
    "channels",
    "users",
    "contacts",
    "conversations",
    "messages",
    "bookings",
    "event_registrations",
    "notes",
    "jobs",
    "audit_events",
    "wa_billable",
    "bot_turns",
    "quick_answers",
    "quick_answer_history",
}


@pytest.fixture
def conn(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as c:
        yield c


def one(conn, query, params=()):
    return conn.execute(query, params).fetchone()[0]


def insert(conn, table, **values):
    """INSERT one row; column names are composed safely with sql.Identifier."""
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, values)),
        sql.SQL(", ").join(sql.Placeholder() * len(values)),
    )
    return conn.execute(query, tuple(values.values())).fetchone()[0]


def tenant(conn, slug="acme", **cols):
    base = {"slug": slug, "name": "Acme", "fallback_text": "A counsellor will reply soon."}
    return insert(conn, "tenants", **{**base, **cols})


def channel(conn, t, type_="messenger", external_id=None):
    if external_id is None and type_ != "web":
        external_id = f"page-{t}-{type_}"
    return insert(conn, "channels", tenant_id=t, type=type_, external_id=external_id)


def contact(conn, t, ch, ext="user-1", **cols):
    return insert(conn, "contacts", tenant_id=t, channel_id=ch, external_user_id=ext, **cols)


def conversation(conn, t, c):
    return insert(conn, "conversations", tenant_id=t, contact_id=c)


def message(conn, t, conv, external_id=None, **cols):
    base = {"role": "student", "content": "hi", "external_id": external_id}
    return insert(conn, "messages", tenant_id=t, conversation_id=conv, **{**base, **cols})


def branch(conn, t, name="Banani"):
    return insert(conn, "branches", tenant_id=t, name=name)


def user(conn, t, email="a@x.com", role="counsellor"):
    return insert(conn, "users", tenant_id=t, email=email, password_hash="h", role=role)


@pytest.fixture
def world(conn):
    """Two tenants, each with a channel, branch, user, contact and conversation."""
    ids = {}
    for key in ("a", "b"):
        t = tenant(conn, slug=f"tenant-{key}")
        ch = channel(conn, t)
        c = contact(conn, t, ch)
        ids[key] = {
            "t": t,
            "ch": ch,
            "br": branch(conn, t),
            "u": user(conn, t, email=f"{key}@x.com"),
            "c": c,
            "conv": conversation(conn, t, c),
        }
    return ids


# ---------- shape ----------


def test_all_tables_exist(conn):
    names = {
        r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    }
    assert names == EXPECTED_TABLES


def test_no_timestamp_without_time_zone(conn):
    bad = conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND data_type = 'timestamp without time zone'"
    ).fetchall()
    assert bad == []


def test_created_at_columns_default_to_now(conn):
    rows = conn.execute(
        "SELECT table_name, column_default, is_nullable FROM information_schema.columns "
        "WHERE table_schema='public' AND column_name='created_at'"
    ).fetchall()
    assert len(rows) >= 12
    for table, default, nullable in rows:
        assert default == "now()", table
        assert nullable == "NO", table


def test_no_floating_point_columns(conn):
    bad = conn.execute(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND data_type IN ('real', 'double precision')"
    ).fetchall()
    assert bad == []


def test_cost_is_exact_numeric(conn):
    row = conn.execute(
        "SELECT data_type, numeric_precision, numeric_scale FROM information_schema.columns "
        "WHERE table_name='bot_turns' AND column_name='cost_usd'"
    ).fetchone()
    assert row == ("numeric", 10, 6)


def test_every_tenant_table_has_a_tenant_index(conn):
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema='public' AND column_name='tenant_id'"
        )
    ]
    for table in tables:
        indexed = one(
            conn,
            "SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid "
            "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = i.indkey[0] "
            "WHERE c.relname = %s AND a.attname = 'tenant_id'",
            (table,),
        )
        assert indexed >= 1, table


def test_jobs_queue_index(conn):
    assert (
        one(
            conn, "SELECT count(*) FROM pg_indexes WHERE indexdef LIKE '%%jobs%%(status, run_at)%%'"
        )
        == 1
    )


# ---------- tenants ----------


@pytest.mark.parametrize(
    "cols",
    [
        {"slug": "Acme"},  # uppercase
        {"slug": "a"},  # too short
        {"slug": "-acme"},
        {"slug": "acme_1"},
        {"slug": "a" * 41},
        {"name": ""},
        {"name": "   "},
        {"country_code": "bd"},
        {"country_code": "BGD"},
        {"currency": "tk"},
        {"model": "gpt-5"},
        {"cache_ttl": "10m"},
        {"monthly_conversation_quota": 0},
        {"monthly_conversation_quota": 500, "hard_cap": 499},
        {"bot_pause_hours": 0},
        {"bot_pause_hours": 169},
        {"fallback_text": ""},
        {"data_region": "mars"},
        {"widget_theme": "[1, 2]"},
        {"crm_webhook_url": "http://crm.example.com"},  # not https
        {"crm_webhook_url": "https://crm.example.com"},  # url without secret
        {"crm_webhook_secret_enc": b"x"},  # secret without url
    ],
)
def test_tenant_rejects_invalid_values(conn, cols):
    with pytest.raises(errors.CheckViolation):
        tenant(conn, **{"slug": "ok-slug", **cols})


def test_tenant_defaults(conn):
    t = tenant(conn)
    row = conn.execute(
        "SELECT country_code, timezone, currency, model, cache_ttl, data_region, active, "
        "bot_pause_hours, languages, allowed_origins, widget_theme FROM tenants WHERE id=%s",
        (t,),
    ).fetchone()
    assert row == (
        "BD",
        "Asia/Dhaka",
        "BDT",
        "claude-haiku-4-5",
        "5m",
        "singapore",
        True,
        24,
        [],
        [],
        {},
    )


def test_tenant_industry_default_and_format(conn):
    assert one(conn, "SELECT industry FROM tenants WHERE id=%s", (tenant(conn),)) == "study_abroad"
    tenant(conn, slug="pets", industry="pet_care")
    for bad in ("Pet Care", "pet-care", "1pets", "p", ""):
        with pytest.raises(errors.CheckViolation):
            tenant(conn, slug="bad-industry", industry=bad)


def test_tenant_slug_unique(conn):
    tenant(conn, slug="acme")
    with pytest.raises(errors.UniqueViolation):
        tenant(conn, slug="acme")


def test_valid_crm_webhook_pair(conn):
    tenant(conn, crm_webhook_url="https://crm.example.com/hook", crm_webhook_secret_enc=b"enc")


# ---------- knowledge ----------


def knowledge(conn, t, **cols):
    base = {"content": "x", "token_count": 1, "created_by": "op"}
    return insert(conn, "knowledge_versions", tenant_id=t, **{**base, **cols})


def test_knowledge_cannot_be_published_without_passing_evals(conn):
    t = tenant(conn)
    with pytest.raises(errors.CheckViolation):
        knowledge(conn, t, published_at=NOW)
    knowledge(conn, t, eval_passed=True, published_at=NOW)


@pytest.mark.parametrize("content, tokens", [("", 1), ("  ", 1), ("x", -1)])
def test_knowledge_rejects_empty_or_negative(conn, content, tokens):
    with pytest.raises(errors.CheckViolation):
        knowledge(conn, tenant(conn), content=content, token_count=tokens)


# ---------- branches, schedules, holidays, events ----------


def test_branch_names_unique_per_tenant_case_insensitive(conn, world):
    with pytest.raises(errors.UniqueViolation):
        branch(conn, world["a"]["t"], "banani")
    branch(conn, world["b"]["t"], "Dhanmondi")


def schedule(conn, t, br, weekday=1, start="10:00", end="12:00", minutes=30, capacity=1):
    return insert(
        conn,
        "schedules",
        tenant_id=t,
        branch_id=br,
        weekday=weekday,
        start_time=start,
        end_time=end,
        slot_minutes=minutes,
        capacity=capacity,
    )


@pytest.mark.parametrize(
    "weekday, start, end, minutes, capacity",
    [
        (0, "10:00", "12:00", 30, 1),
        (8, "10:00", "12:00", 30, 1),
        (1, "12:00", "12:00", 30, 1),  # end not after start
        (1, "12:00", "10:00", 30, 1),
        (1, "10:00", "12:00", 9, 1),
        (1, "10:00", "12:00", 241, 1),
        (1, "10:00", "12:00", 30, 0),
    ],
)
def test_schedule_rejects_invalid(conn, world, weekday, start, end, minutes, capacity):
    w = world["a"]
    with pytest.raises(errors.CheckViolation):
        schedule(conn, w["t"], w["br"], weekday, start, end, minutes, capacity)


def test_schedule_valid_boundaries(conn, world):
    w = world["a"]
    schedule(conn, w["t"], w["br"], weekday=7, minutes=10, capacity=1)
    schedule(conn, w["t"], w["br"], weekday=1, minutes=240)


def test_schedule_cannot_use_another_tenants_branch(conn, world):
    with pytest.raises(errors.ForeignKeyViolation):
        schedule(conn, world["a"]["t"], world["b"]["br"])


def test_holiday_once_per_date(conn, world):
    t = world["a"]["t"]
    conn.execute("INSERT INTO holidays (tenant_id, date) VALUES (%s, '2026-12-16')", (t,))
    with pytest.raises(errors.UniqueViolation):
        conn.execute("INSERT INTO holidays (tenant_id, date) VALUES (%s, '2026-12-16')", (t,))


@pytest.mark.parametrize("title, capacity", [("", 10), (" ", 10), ("Seminar", 0)])
def test_event_rejects_invalid(conn, world, title, capacity):
    with pytest.raises(errors.CheckViolation):
        insert(
            conn, "events", tenant_id=world["a"]["t"], title=title, starts_at=NOW, capacity=capacity
        )


def test_event_cannot_use_another_tenants_branch(conn, world):
    with pytest.raises(errors.ForeignKeyViolation):
        insert(
            conn,
            "events",
            tenant_id=world["a"]["t"],
            title="x",
            starts_at=NOW,
            branch_id=world["b"]["br"],
        )


# ---------- channels ----------


def test_channel_type_checked(conn, world):
    with pytest.raises(errors.CheckViolation):
        channel(conn, world["a"]["t"], "sms", "123")


def test_non_web_channel_needs_external_id(conn, world):
    with pytest.raises(errors.CheckViolation):
        conn.execute(
            "INSERT INTO channels (tenant_id, type) VALUES (%s, 'telegram')", (world["a"]["t"],)
        )


def test_channel_external_id_unique_per_type(conn, world):
    channel(conn, world["a"]["t"], "whatsapp", "+8801700000000")
    with pytest.raises(errors.UniqueViolation):
        channel(conn, world["b"]["t"], "whatsapp", "+8801700000000")
    channel(conn, world["b"]["t"], "telegram", "+8801700000000")  # same id, other type: fine


def test_one_web_channel_per_tenant(conn, world):
    channel(conn, world["a"]["t"], "web")
    with pytest.raises(errors.UniqueViolation):
        channel(conn, world["a"]["t"], "web")
    channel(conn, world["b"]["t"], "web")


# ---------- users ----------


def test_user_email_unique_case_insensitive(conn, world):
    with pytest.raises(errors.UniqueViolation):
        user(conn, world["b"]["t"], email="A@X.COM")


@pytest.mark.parametrize(
    "has_tenant, role",
    [(True, "operator"), (False, "counsellor"), (False, "tenant_admin"), (True, "owner")],
)
def test_user_role_matches_tenant(conn, world, has_tenant, role):
    t = world["a"]["t"] if has_tenant else None
    with pytest.raises(errors.CheckViolation):
        user(conn, t, email="new@x.com", role=role)


def test_operator_user_without_tenant(conn):
    user(conn, None, email="op@x.com", role="operator")


@pytest.mark.parametrize("email", ["", "no-at-sign", "a@", "@b.com", "a b@c.com"])
def test_user_email_format(conn, world, email):
    with pytest.raises(errors.CheckViolation):
        user(conn, world["a"]["t"], email=email)


# ---------- contacts ----------


def test_contact_unique_per_channel(conn, world):
    w = world["a"]
    with pytest.raises(errors.UniqueViolation):
        contact(conn, w["t"], w["ch"], "user-1")


def test_contact_cannot_use_another_tenants_channel(conn, world):
    with pytest.raises(errors.ForeignKeyViolation):
        contact(conn, world["a"]["t"], world["b"]["ch"], "x")


def test_contact_orphan_channel_rejected(conn, world):
    with pytest.raises(errors.ForeignKeyViolation):
        contact(conn, world["a"]["t"], 999_999, "x")


@pytest.mark.parametrize(
    "cols",
    [
        {"phone": "01712345678"},  # not E.164
        {"phone": "+0171234567"},
        {"phone": "+88017123456789012"},  # too long
        {"score": "hottest"},
        {"status": "maybe"},
        {"status": "enrolled"},  # consultancy-specific stage, replaced in 002
        {"status": "counselling_booked"},
        {"profile": "[]"},
        {"source_ad": '"ad"'},
    ],
)
def test_contact_rejects_invalid(conn, world, cols):
    w = world["a"]
    with pytest.raises(errors.CheckViolation):
        contact(conn, w["t"], w["ch"], "new-user", **cols)


def test_contact_valid_values(conn, world):
    w = world["a"]
    contact(
        conn,
        w["t"],
        w["ch"],
        "u2",
        phone="+8801712345678",
        adult=True,
        score="hot",
        status="booked",
        profile='{"intake": "2027-01"}',
    )
    contact(conn, w["t"], w["ch"], "u3", adult=False)  # minor without phone


@pytest.mark.parametrize(
    "stage", ["new", "contacted", "qualified", "booked", "in_progress", "won", "lost"]
)
def test_contact_generic_stages(conn, world, stage):
    w = world["a"]
    contact(conn, w["t"], w["ch"], f"stage-{stage}", status=stage)


def test_minor_phone_is_stored_owner_decision(conn, world):
    # D-014: the owner chose to store every phone number, including under-18s.
    w = world["a"]
    c = contact(conn, w["t"], w["ch"], "minor", adult=False, phone="+8801712345678")
    assert one(conn, "SELECT phone FROM contacts WHERE id=%s", (c,)) == "+8801712345678"


def test_contact_assignee_must_be_same_tenant(conn, world):
    w = world["a"]
    with pytest.raises(errors.ForeignKeyViolation):
        contact(conn, w["t"], w["ch"], "u4", assignee_user_id=world["b"]["u"])
    contact(conn, w["t"], w["ch"], "u5", assignee_user_id=w["u"])


def test_contact_updated_at_moves_on_update(conn, world):
    w = world["a"]
    before = one(conn, "SELECT updated_at FROM contacts WHERE id=%s", (w["c"],))
    conn.execute("SELECT pg_sleep(0.01)")
    conn.execute("UPDATE contacts SET name='Rahim' WHERE id=%s", (w["c"],))
    after = one(conn, "SELECT updated_at FROM contacts WHERE id=%s", (w["c"],))
    assert after > before


# ---------- conversations and messages ----------


def test_conversation_state_checked(conn, world):
    with pytest.raises(errors.CheckViolation):
        conn.execute("UPDATE conversations SET state='paused' WHERE id=%s", (world["a"]["conv"],))


def test_conversation_streak_not_negative(conn, world):
    with pytest.raises(errors.CheckViolation):
        conn.execute(
            "UPDATE conversations SET unanswered_streak=-1 WHERE id=%s", (world["a"]["conv"],)
        )


def test_conversation_cannot_use_another_tenants_contact(conn, world):
    with pytest.raises(errors.ForeignKeyViolation):
        conversation(conn, world["a"]["t"], world["b"]["c"])


def test_message_role_checked(conn, world):
    w = world["a"]
    with pytest.raises(errors.CheckViolation):
        message(conn, w["t"], w["conv"], role="assistant")


def test_message_external_id_null_many_times(conn, world):
    w = world["a"]
    message(conn, w["t"], w["conv"])
    message(conn, w["t"], w["conv"])


def test_message_external_id_unique_per_conversation(conn, world):
    w = world["a"]
    message(conn, w["t"], w["conv"], "mid.1")
    with pytest.raises(errors.UniqueViolation):
        message(conn, w["t"], w["conv"], "mid.1")
    message(conn, world["b"]["t"], world["b"]["conv"], "mid.1")  # other conversation: fine


@pytest.mark.parametrize(
    "cols",
    [
        {"content": ""},
    ],
)
def test_message_rejects_invalid(conn, world, cols):
    w = world["a"]
    with pytest.raises(errors.CheckViolation):
        message(conn, w["t"], w["conv"], **cols)


def test_messages_hold_content_only(conn):
    cols = [
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='messages'"
            " ORDER BY ordinal_position"
        )
    ]
    assert cols == [
        "id",
        "tenant_id",
        "conversation_id",
        "role",
        "content",
        "external_id",
        "created_at",
    ]


# ---------- bot_turns (performance log, D-013) ----------


def turn(conn, t, conv, **cols):
    base = {"source": "llm", "channel": "messenger", "model": "claude-haiku-4-5"}
    return insert(conn, "bot_turns", tenant_id=t, conversation_id=conv, **{**base, **cols})


def test_bot_turn_full_row(conn, world):
    w = world["a"]
    tid = turn(
        conn,
        w["t"],
        w["conv"],
        message_id=123,
        received_at=NOW,
        language="banglish",
        latency_ms=2300,
        llm_ms=1900,
        input_tokens=1500,
        cache_read_tokens=1200,
        cache_write_tokens=0,
        output_tokens=180,
        cost_usd="0.000123",
        tool_calls=["update_profile", "list_slots"],
        stop_reason="end_turn",
    )
    row = conn.execute(
        "SELECT cost_usd, tool_calls, created_at IS NOT NULL FROM bot_turns WHERE id=%s", (tid,)
    ).fetchone()
    assert (str(row[0]), row[1], row[2]) == ("0.000123", ["update_profile", "list_slots"], True)


@pytest.mark.parametrize(
    "cols",
    [
        {"source": "magic"},
        {"channel": "sms"},
        {"language": "klingon"},
        {"latency_ms": -1},
        {"llm_ms": -1},
        {"input_tokens": -1},
        {"cache_read_tokens": -1},
        {"cache_write_tokens": -1},
        {"output_tokens": -1},
        {"cost_usd": "-0.000001"},
        {"source": "llm", "model": None},  # an AI reply must name its model
        {"source": "quick", "model": None, "cost_usd": "0.01"},  # button answers cost nothing
        {"error_code": "x" * 101},
    ],
)
def test_bot_turn_rejects_invalid(conn, world, cols):
    w = world["a"]
    with pytest.raises(errors.CheckViolation):
        turn(conn, w["t"], w["conv"], **cols)


def test_bot_turn_quick_answer_without_model(conn, world):
    w = world["a"]
    turn(conn, w["t"], w["conv"], source="quick", model=None, cost_usd="0")


def test_bot_turn_cannot_use_another_tenants_conversation(conn, world):
    with pytest.raises(errors.ForeignKeyViolation):
        turn(conn, world["a"]["t"], world["b"]["conv"])


def test_bot_turn_survives_message_deletion(conn, world):
    # Metrics outlive message text (retention deletes messages, keeps performance history).
    w = world["a"]
    m = message(conn, w["t"], w["conv"], role="bot", content="reply")
    turn(conn, w["t"], w["conv"], message_id=m)
    conn.execute("DELETE FROM messages WHERE id=%s", (m,))
    assert one(conn, "SELECT count(*) FROM bot_turns WHERE message_id=%s", (m,)) == 1


def test_bot_turns_hold_no_text_columns(conn):
    # Only metadata: no free-text column could hold a message or phone number.
    text_cols = {
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name='bot_turns' AND data_type IN ('text', 'jsonb')"
        )
    }
    assert text_cols == {"source", "channel", "model", "language", "stop_reason", "error_code"}


def test_message_cannot_use_another_tenants_conversation(conn, world):
    with pytest.raises(errors.ForeignKeyViolation):
        message(conn, world["a"]["t"], world["b"]["conv"])


# ---------- bookings, events, notes ----------


def booking(conn, t, c, br, slot="2026-10-01 11:00+06", status="booked"):
    return one(
        conn,
        "INSERT INTO bookings (tenant_id, contact_id, branch_id, slot_start, status)"
        " VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (t, c, br, slot, status),
    )


def test_booking_status_checked(conn, world):
    w = world["a"]
    with pytest.raises(errors.CheckViolation):
        booking(conn, w["t"], w["c"], w["br"], status="maybe")


def test_booking_no_double_booking_same_slot(conn, world):
    w = world["a"]
    b = booking(conn, w["t"], w["c"], w["br"])
    with pytest.raises(errors.UniqueViolation):
        booking(conn, w["t"], w["c"], w["br"])
    conn.execute("UPDATE bookings SET status='cancelled' WHERE id=%s", (b,))
    booking(conn, w["t"], w["c"], w["br"])  # after cancelling, the student can rebook


def test_booking_cannot_mix_tenants(conn, world):
    a, b = world["a"], world["b"]
    with pytest.raises(errors.ForeignKeyViolation):
        booking(conn, a["t"], a["c"], b["br"])
    with pytest.raises(errors.ForeignKeyViolation):
        booking(conn, a["t"], b["c"], a["br"])


def test_booking_reminder_state_checked(conn, world):
    w = world["a"]
    b = booking(conn, w["t"], w["c"], w["br"])
    with pytest.raises(errors.CheckViolation):
        conn.execute("UPDATE bookings SET reminder_state='sent_twice' WHERE id=%s", (b,))


def test_event_registration_once_per_contact(conn, world):
    w = world["a"]
    e = one(
        conn,
        "INSERT INTO events (tenant_id, title, starts_at) VALUES (%s, 'Fair', now()) RETURNING id",
        (w["t"],),
    )
    sql = "INSERT INTO event_registrations (tenant_id, event_id, contact_id) VALUES (%s, %s, %s)"
    conn.execute(sql, (w["t"], e, w["c"]))
    with pytest.raises(errors.UniqueViolation):
        conn.execute(sql, (w["t"], e, w["c"]))
    with pytest.raises(errors.ForeignKeyViolation):
        conn.execute(sql, (world["b"]["t"], e, world["b"]["c"]))  # event of another tenant


def test_note_body_required_and_tenant_matched(conn, world):
    a, b = world["a"], world["b"]
    sql = "INSERT INTO notes (tenant_id, contact_id, user_id, body) VALUES (%s, %s, %s, %s)"
    with pytest.raises(errors.CheckViolation):
        conn.execute(sql, (a["t"], a["c"], a["u"], " "))
    with pytest.raises(errors.ForeignKeyViolation):
        conn.execute(sql, (a["t"], b["c"], a["u"], "call back"))
    conn.execute(sql, (a["t"], a["c"], a["u"], "call back"))


# ---------- jobs, audit, WhatsApp billing ----------


@pytest.mark.parametrize(
    "cols",
    [
        {"status": "later"},
        {"attempts": -1},
        {"max_attempts": 0},
        {"attempts": 7, "max_attempts": 6},
        {"kind": ""},
        {"payload": "[]"},
    ],
)
def test_job_rejects_invalid(conn, cols):
    with pytest.raises(errors.CheckViolation):
        insert(conn, "jobs", **{"kind": "send", "payload": "{}", **cols})


def test_job_defaults(conn):
    row = conn.execute(
        "INSERT INTO jobs (kind) VALUES ('send') RETURNING status, attempts, max_attempts, payload"
    ).fetchone()
    assert row == ("pending", 0, 6, {})


def test_audit_event_may_be_global_but_conversation_must_match_tenant(conn, world):
    conn.execute("INSERT INTO audit_events (kind) VALUES ('startup')")
    with pytest.raises(errors.ForeignKeyViolation):
        insert(
            conn,
            "audit_events",
            tenant_id=world["a"]["t"],
            conversation_id=world["b"]["conv"],
            kind="handoff",
        )
    with pytest.raises(errors.CheckViolation):
        conn.execute("INSERT INTO audit_events (kind) VALUES ('')")
    with pytest.raises(errors.CheckViolation):  # global event can't sneak in a conversation
        conn.execute(
            "INSERT INTO audit_events (conversation_id, kind) VALUES (%s, 'x')",
            (world["b"]["conv"],),
        )


@pytest.mark.parametrize(
    "month, category, count",
    [("2026-10-02", "utility", 1), ("2026-10-01", "free", 1), ("2026-10-01", "utility", -1)],
)
def test_wa_billable_rejects_invalid(conn, world, month, category, count):
    with pytest.raises(errors.CheckViolation):
        conn.execute(
            "INSERT INTO wa_billable (tenant_id, month, category, count) VALUES (%s, %s, %s, %s)",
            (world["a"]["t"], month, category, count),
        )


def test_wa_billable_one_row_per_month_and_category(conn, world):
    row = {"tenant_id": world["a"]["t"], "month": "2026-10-01", "category": "utility", "count": 1}
    insert(conn, "wa_billable", **row)
    with pytest.raises(errors.UniqueViolation):
        insert(conn, "wa_billable", **row)


# ---------- deleting ----------


def test_deleting_tenant_with_data_is_refused(conn, world):
    with pytest.raises(errors.ForeignKeyViolation):
        conn.execute("DELETE FROM tenants WHERE id=%s", (world["a"]["t"],))
    assert one(conn, "SELECT count(*) FROM contacts") == 2  # nothing silently cascaded


def test_no_foreign_key_cascades_or_nulls_anything(conn):
    # Regression (P1.2 mutation check): the delete-refused test above passes as long as ANY
    # table blocks the delete, so a cascade on a single table went unnoticed. Check every FK.
    rows = conn.execute(
        "SELECT conrelid::regclass::text, conname, confdeltype, confupdtype "
        "FROM pg_constraint WHERE contype = 'f' ORDER BY 1, 2"
    ).fetchall()
    assert len(rows) >= 20
    bad = [
        (table, name)
        for table, name, on_delete, on_update in rows
        if (on_delete, on_update) != ("a", "a")
    ]
    assert bad == []  # 'a' = NO ACTION


def test_deleting_empty_tenant_is_allowed(conn):
    t = tenant(conn, slug="empty")
    conn.execute("DELETE FROM tenants WHERE id=%s", (t,))
    assert one(conn, "SELECT count(*) FROM tenants WHERE id=%s", (t,)) == 0
