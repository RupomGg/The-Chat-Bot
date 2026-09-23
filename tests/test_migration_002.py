"""Upgrade path 001 → 002 (universal core, D-012; performance log, D-013; minors, D-014).

A database at 001 holds old-style data; applying 002 must keep every row and map it.
"""

import shutil
from decimal import Decimal

import psycopg
import pytest

from app.db import MIGRATIONS_DIR, migrate

OLD_TO_NEW = {
    "new": "new",
    "contacted": "contacted",
    "counselling_booked": "booked",
    "counselled": "in_progress",
    "applied": "in_progress",
    "enrolled": "won",
    "lost": "lost",
}


@pytest.fixture
def at_001(db_url, tmp_path):
    """A database migrated to 001 only, filled with old-style rows."""
    for name in ("000_schema_version.sql", "001_init.sql"):
        shutil.copyfile(MIGRATIONS_DIR / name, tmp_path / name)
    migrate(db_url, tmp_path)
    with psycopg.connect(db_url, autocommit=True) as conn:
        t = conn.execute(
            "INSERT INTO tenants (slug, name, fallback_text)"
            " VALUES ('acme', 'Acme', 'x') RETURNING id"
        ).fetchone()[0]
        ch = conn.execute(
            "INSERT INTO channels (tenant_id, type, external_id)"
            " VALUES (%s, 'whatsapp', 'pn-1') RETURNING id",
            (t,),
        ).fetchone()[0]
        contacts = {}
        for old in OLD_TO_NEW:
            contacts[old] = conn.execute(
                "INSERT INTO contacts (tenant_id, channel_id, external_user_id, status)"
                " VALUES (%s, %s, %s, %s) RETURNING id",
                (t, ch, f"user-{old}", old),
            ).fetchone()[0]
        conv = conn.execute(
            "INSERT INTO conversations (tenant_id, contact_id) VALUES (%s, %s) RETURNING id",
            (t, contacts["new"]),
        ).fetchone()[0]
        usage = (
            "INSERT INTO messages (tenant_id, conversation_id, role, content, model, input_tokens,"
            " cache_read_tokens, cache_write_tokens, output_tokens, cost_usd)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"
        )
        ids = {
            "student": conn.execute(
                "INSERT INTO messages (tenant_id, conversation_id, role, content)"
                " VALUES (%s, %s, 'student', 'hi') RETURNING id",
                (t, conv),
            ).fetchone()[0],
            "llm": conn.execute(
                usage,
                (t, conv, "bot", "hello", "claude-haiku-4-5", 1200, 900, 50, 80, "0.001234"),
            ).fetchone()[0],
            "quick": conn.execute(
                usage, (t, conv, "bot", "fees...", "quick", None, None, None, None, None)
            ).fetchone()[0],
        }
    return {"url": db_url, "dir": tmp_path, "t": t, "conv": conv, "contacts": contacts, "ids": ids}


def upgrade(state):
    shutil.copyfile(
        MIGRATIONS_DIR / "002_universal_core.sql", state["dir"] / "002_universal_core.sql"
    )
    assert migrate(state["url"], state["dir"]) == ["002_universal_core.sql"]
    return psycopg.connect(state["url"], autocommit=True)


def test_old_statuses_are_mapped_to_generic_stages(at_001):
    with upgrade(at_001) as conn:
        for old, new in OLD_TO_NEW.items():
            got = conn.execute(
                "SELECT status FROM contacts WHERE id = %s", (at_001["contacts"][old],)
            ).fetchone()[0]
            assert got == new, old


def test_no_contact_or_message_is_lost(at_001):
    with upgrade(at_001) as conn:
        assert conn.execute("SELECT count(*) FROM contacts").fetchone()[0] == len(OLD_TO_NEW)
        assert conn.execute("SELECT count(*) FROM messages").fetchone()[0] == 3


def test_existing_usage_moves_to_bot_turns(at_001):
    with upgrade(at_001) as conn:
        rows = conn.execute(
            "SELECT message_id, source, channel, model, input_tokens, cache_read_tokens,"
            " cache_write_tokens, output_tokens, cost_usd, latency_ms"
            " FROM bot_turns ORDER BY message_id"
        ).fetchall()
    ids = at_001["ids"]
    assert rows == [
        (
            ids["llm"],
            "llm",
            "whatsapp",
            "claude-haiku-4-5",
            1200,
            900,
            50,
            80,
            Decimal("0.001234"),
            None,
        ),
        (ids["quick"], "quick", "whatsapp", None, None, None, None, None, None, None),
    ]


def test_messages_keep_content_only(at_001):
    with upgrade(at_001) as conn:
        cols = [
            r[0]
            for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'messages'"
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


def test_existing_tenants_get_the_first_industry(at_001):
    with upgrade(at_001) as conn:
        assert conn.execute("SELECT industry FROM tenants").fetchone()[0] == "study_abroad"
