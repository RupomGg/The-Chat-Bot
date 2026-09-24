"""Migration 003 (D-015): contact email, tenant pack settings, quick answers + history."""

import threading

import psycopg
import pytest
from psycopg import errors, sql

# ---------- helpers ----------


@pytest.fixture
def conn(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as c:
        yield c


def one(conn, query, params=()):
    return conn.execute(query, params).fetchone()[0]


def insert(conn, table, **values):
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, values)),
        sql.SQL(", ").join(sql.Placeholder() * len(values)),
    )
    return conn.execute(query, tuple(values.values())).fetchone()[0]


def tenant(conn, slug="acme"):
    return insert(conn, "tenants", slug=slug, name="Acme", fallback_text="x")


def qa(conn, t, code="FEES", triggers=("fees",), answers='{"en": "Counselling is free."}', **cols):
    return insert(
        conn,
        "quick_answers",
        tenant_id=t,
        code=code,
        triggers=list(triggers),
        answers=answers,
        **cols,
    )


@pytest.fixture
def two(conn):
    return tenant(conn, "tenant-a"), tenant(conn, "tenant-b")


# ---------- contacts.email ----------


def contact(conn, t, **cols):
    ch = insert(conn, "channels", tenant_id=t, type="web")
    return insert(conn, "contacts", tenant_id=t, channel_id=ch, external_user_id="v1", **cols)


@pytest.mark.parametrize(
    "email",
    ["rahim@gmail.com", "Rahim.Uddin+visa@consult.com.bd", "a@b.co", "x@" + "d" * 240 + ".com"],
)
def test_valid_emails_stored(conn, email):
    c = contact(conn, tenant(conn), email=email)
    assert one(conn, "SELECT email FROM contacts WHERE id=%s", (c,)) == email


@pytest.mark.parametrize(
    "email",
    [
        "",
        "rahim",
        "rahim@",
        "@gmail.com",
        "rahim@gmail",
        "a b@c.com",
        "a@@b.com",
        "x@" + "d" * 250 + ".com",
    ],
)
def test_invalid_emails_rejected(conn, email):
    with pytest.raises(errors.CheckViolation):
        contact(conn, tenant(conn), email=email)


def test_email_optional(conn):
    c = contact(conn, tenant(conn))
    assert one(conn, "SELECT email FROM contacts WHERE id=%s", (c,)) is None


# ---------- tenants.settings ----------


def test_tenant_settings_default_and_shape(conn):
    t = tenant(conn)
    assert one(conn, "SELECT settings FROM tenants WHERE id=%s", (t,)) == {}
    conn.execute(
        "UPDATE tenants SET settings = %s WHERE id=%s", ('{"served_countries": ["uk"]}', t)
    )
    with pytest.raises(errors.CheckViolation):
        conn.execute("UPDATE tenants SET settings = '[]' WHERE id=%s", (t,))


# ---------- quick_answers ----------


def test_quick_answer_row_and_defaults(conn, two):
    q = qa(conn, two[0], buttons=["BOOK"])
    row = conn.execute(
        "SELECT code, triggers, answers, buttons, action, active, created_at IS NOT NULL"
        " FROM quick_answers WHERE id=%s",
        (q,),
    ).fetchone()
    assert row == ("FEES", ["fees"], {"en": "Counselling is free."}, ["BOOK"], None, True, True)


@pytest.mark.parametrize("code", ["fees", "F", "FEES-UK", "1FEES", "F" * 41, ""])
def test_code_format(conn, two, code):
    with pytest.raises(errors.CheckViolation):
        qa(conn, two[0], code=code)


def test_code_unique_per_tenant_only(conn, two):
    qa(conn, two[0])
    with pytest.raises(errors.UniqueViolation):
        qa(conn, two[0], triggers=("other",))
    qa(conn, two[1])  # same code, another company: fine


@pytest.mark.parametrize(
    "cols",
    [
        {"answers": "[]"},  # not an object
        {"answers": "{}"},  # no answer and no action
        {"answers": '{"en": ""}'},  # empty answer text
        {"answers": '{"en": 5}'},  # not text
        {"answers": '{"english": "x"}'},  # bad language code
        {"action": "delete_everything"},
        {"triggers": [""]},
        {"triggers": [" fees"]},  # untrimmed
        {"triggers": ["Fees"]},  # not lower-cased by the app
        {"buttons": [""]},
    ],
)
def test_quick_answer_rejects_invalid(conn, two, cols):
    with pytest.raises(errors.CheckViolation):
        qa(conn, two[0], **cols)


def test_action_without_answer_text_allowed(conn, two):
    qa(conn, two[0], code="BOOK", triggers=("book",), answers="{}", action="start_booking")


def test_bangla_trigger_and_answer(conn, two):
    q = qa(conn, two[0], triggers=("খরচ কত", "fees"), answers='{"bn": "কাউন্সেলিং ফ্রি।"}')
    assert one(conn, "SELECT triggers FROM quick_answers WHERE id=%s", (q,)) == ["খরচ কত", "fees"]


# ---------- the same trigger can't belong to two quick answers of one company ----------


def test_overlapping_trigger_rejected_on_insert(conn, two):
    qa(conn, two[0], code="FEES", triggers=("fees", "cost"))
    with pytest.raises(errors.UniqueViolation, match="cost"):
        qa(conn, two[0], code="PRICE", triggers=("price", "cost"))


def test_overlapping_trigger_rejected_on_update(conn, two):
    qa(conn, two[0], code="FEES", triggers=("fees",))
    q = qa(conn, two[0], code="OFFICE", triggers=("address",))
    with pytest.raises(errors.UniqueViolation):
        conn.execute("UPDATE quick_answers SET triggers = '{address,fees}' WHERE id=%s", (q,))


def test_duplicate_trigger_inside_one_row_rejected(conn, two):
    with pytest.raises(errors.UniqueViolation):
        qa(conn, two[0], triggers=("fees", "fees"))


def test_updating_a_row_keeps_its_own_triggers(conn, two):
    q = qa(conn, two[0], triggers=("fees",))
    conn.execute('UPDATE quick_answers SET answers = \'{"en": "New text"}\' WHERE id=%s', (q,))


def test_same_trigger_in_two_companies_fine(conn, two):
    qa(conn, two[0], triggers=("fees",))
    qa(conn, two[1], triggers=("fees",))


def test_inactive_row_still_reserves_its_triggers(conn, two):
    # A switched-off answer can be switched back on; it must not collide then.
    qa(conn, two[0], code="FEES", triggers=("fees",), active=False)
    with pytest.raises(errors.UniqueViolation):
        qa(conn, two[0], code="PRICE", triggers=("fees",))


def test_two_admins_saving_the_same_trigger_at_once(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as setup:
        t = tenant(setup)
    first = psycopg.connect(migrated_db_url)
    second = psycopg.connect(migrated_db_url)
    outcome = {}
    try:
        qa(first, t, code="FEES", triggers=("fees",))  # open transaction, not committed yet

        def other_admin():
            try:
                qa(second, t, code="PRICE", triggers=("fees",))
                second.commit()
                outcome["second"] = "saved"
            except errors.UniqueViolation:
                second.rollback()
                outcome["second"] = "rejected"

        worker = threading.Thread(target=other_admin)
        worker.start()
        worker.join(timeout=1)
        assert worker.is_alive()  # the second save waits for the first
        first.commit()
        worker.join(timeout=10)
        assert outcome == {"second": "rejected"}
    finally:
        first.close()
        second.close()


# ---------- automatic history ----------


def history(conn, q):
    return conn.execute(
        "SELECT operation, before, after, changed_by FROM quick_answer_history"
        " WHERE quick_answer_id=%s ORDER BY id",
        (q,),
    ).fetchall()


def test_history_records_create_update_delete(conn, two):
    q = qa(conn, two[0])
    conn.execute('UPDATE quick_answers SET answers = \'{"en": "Now ৳500"}\' WHERE id=%s', (q,))
    conn.execute("DELETE FROM quick_answers WHERE id=%s", (q,))
    rows = history(conn, q)
    assert [r[0] for r in rows] == ["insert", "update", "delete"]
    assert rows[0][1] is None and rows[0][2]["answers"] == {"en": "Counselling is free."}
    assert rows[1][1]["answers"] == {"en": "Counselling is free."}
    assert rows[1][2]["answers"] == {"en": "Now ৳500"}
    assert rows[2][1]["answers"] == {"en": "Now ৳500"} and rows[2][2] is None


def test_history_survives_deletion_so_it_can_be_undone(conn, two):
    q = qa(conn, two[0])
    conn.execute("DELETE FROM quick_answers WHERE id=%s", (q,))
    before = history(conn, q)[-1][1]
    assert before["code"] == "FEES" and before["triggers"] == ["fees"]


def test_history_records_who_changed_it(conn, two):
    user = insert(
        conn, "users", tenant_id=two[0], email="admin@a.com", password_hash="h", role="tenant_admin"
    )
    with conn.transaction():
        conn.execute("SELECT set_config('app.user_id', %s, true)", (str(user),))
        q = qa(conn, two[0])
    assert history(conn, q)[0][3] == user


def test_history_without_a_user_is_system(conn, two):
    q = qa(conn, two[0])
    assert history(conn, q)[0][3] is None


def test_history_rows_carry_the_tenant(conn, two):
    q = qa(conn, two[0])
    assert (
        one(conn, "SELECT tenant_id FROM quick_answer_history WHERE quick_answer_id=%s", (q,))
        == two[0]
    )


def test_updated_at_moves(conn, two):
    q = qa(conn, two[0])
    before = one(conn, "SELECT updated_at FROM quick_answers WHERE id=%s", (q,))
    conn.execute("SELECT pg_sleep(0.01)")
    conn.execute("UPDATE quick_answers SET active = false WHERE id=%s", (q,))
    assert one(conn, "SELECT updated_at FROM quick_answers WHERE id=%s", (q,)) > before


def test_deleting_a_tenant_with_quick_answers_is_refused(conn, two):
    qa(conn, two[0])
    with pytest.raises(errors.ForeignKeyViolation):
        conn.execute("DELETE FROM tenants WHERE id=%s", (two[0],))
