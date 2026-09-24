"""Tests for the test-database fixtures in conftest.py (they're code too)."""

import re
import uuid

import psycopg
import pytest
from psycopg import sql

from tests import conftest


def make_db(admin, name):
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')


def exists(admin, name):
    with psycopg.connect(admin) as conn:
        found = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        return found.fetchone() is not None


class RacingConnect:
    """psycopg.connect that fails like an autovacuum race `failures` times, then works."""

    def __init__(self, failures, error):
        self.failures, self.error, self.calls = failures, error, 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error("permission denied to terminate process")
        return REAL_CONNECT(*args, **kwargs)


REAL_CONNECT = psycopg.connect


@pytest.mark.parametrize(
    "error", [psycopg.errors.InsufficientPrivilege, psycopg.errors.ObjectInUse]
)
def test_drop_retries_through_autovacuum_race(monkeypatch, error):
    admin = conftest._test_admin_url()
    name = conftest._new_database_name()
    make_db(admin, name)
    racing = RacingConnect(failures=2, error=error)
    monkeypatch.setattr(psycopg, "connect", racing)
    conftest._drop_database(admin, name)
    monkeypatch.undo()
    assert racing.calls == 3
    assert not exists(admin, name)


def test_drop_gives_up_after_deadline(monkeypatch):
    admin = conftest._test_admin_url()
    racing = RacingConnect(failures=10_000, error=psycopg.errors.InsufficientPrivilege)
    monkeypatch.setattr(psycopg, "connect", racing)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conftest._drop_database(admin, "t_000000000000", retry_for=0.3)
    assert 2 <= racing.calls < 20


def test_drop_other_errors_are_not_retried(monkeypatch):
    racing = RacingConnect(failures=10_000, error=psycopg.errors.SyntaxError)
    monkeypatch.setattr(psycopg, "connect", racing)
    with pytest.raises(psycopg.errors.SyntaxError):
        conftest._drop_database("postgresql://unused/db", "t_000000000000")
    assert racing.calls == 1


def test_clone_retries_while_template_is_in_use(monkeypatch, _migrated_template):
    admin = conftest._test_admin_url()
    name = conftest._new_database_name()
    racing = RacingConnect(failures=2, error=psycopg.errors.ObjectInUse)
    monkeypatch.setattr(psycopg, "connect", racing)
    conftest._clone_database(admin, _migrated_template, name)
    monkeypatch.undo()
    try:
        assert racing.calls == 3
        assert exists(admin, name)
    finally:
        conftest._drop_database(admin, name)


def test_migrated_copy_has_every_migration(migrated_db_url):
    with psycopg.connect(migrated_db_url) as conn:
        names = [r[0] for r in conn.execute("SELECT name FROM schema_version ORDER BY version")]
    assert names == [
        "000_schema_version.sql",
        "001_init.sql",
        "002_universal_core.sql",
        "003_quick_answers_and_contact_details.sql",
    ]


def test_changes_to_a_copy_do_not_reach_the_template(migrated_db_url, _migrated_template):
    with psycopg.connect(migrated_db_url, autocommit=True) as conn:
        conn.execute("INSERT INTO jobs (kind) VALUES ('only-in-this-copy')")
    template_url = conftest._url_for(conftest._test_admin_url(), _migrated_template)
    with psycopg.connect(template_url) as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_second_run_cannot_take_the_session_lock():
    # This run's main process (or another run) holds the lock for the whole run, so a
    # second run gets None and skips cleanup. Also true inside an xdist worker.
    assert conftest._try_session_lock(conftest._test_admin_url()) is None


def test_only_the_main_process_cleans_up(monkeypatch):
    # An xdist worker must never drop leftovers: other workers' databases look like them.
    calls = []
    monkeypatch.setattr(conftest, "_try_session_lock", lambda admin: calls.append(admin))

    class Worker:
        workerinput = {"workerid": "gw0"}

    conftest.pytest_configure(Worker())
    assert calls == []
    assert not hasattr(Worker, "_session_lock")


def test_session_lock_is_exclusive_and_released_on_close():
    admin = conftest._test_admin_url()
    key = 900_000_000 + uuid.uuid4().int % 1_000_000  # private key: can't clash with real runs
    first = conftest._try_session_lock(admin, key)
    assert first is not None
    assert conftest._try_session_lock(admin, key) is None  # a second run is refused
    first.close()
    again = conftest._try_session_lock(admin, key)  # released when the holder closes
    assert again is not None
    again.close()


def test_leftovers_excludes_this_runs_databases():
    admin = conftest._test_admin_url()
    stranger = "t_" + uuid.uuid4().hex[:12]  # like a crashed earlier run's database
    mine = conftest._new_database_name()
    make_db(admin, stranger)
    make_db(admin, mine)
    try:
        found = conftest._leftovers(admin, conftest.OWN_DATABASES)
        assert stranger in found
        assert mine not in found
        assert not set(found) & conftest.OWN_DATABASES
    finally:
        conftest._drop_database(admin, stranger)
        conftest._drop_database(admin, mine)


def test_every_fixture_database_is_registered(db_url, migrated_db_url, _migrated_template):
    for url in (db_url, migrated_db_url):
        assert url.rsplit("/", 1)[1] in conftest.OWN_DATABASES
    assert _migrated_template in conftest.OWN_DATABASES


def test_drop_missing_database_is_fine():
    conftest._drop_database(conftest._test_admin_url(), "t_" + uuid.uuid4().hex[:12])


@pytest.mark.parametrize(
    "name, matches",
    [
        ("t_28df69728aa2", True),
        ("t_28DF69728AA2", False),  # uppercase: not ours
        ("t_28df69728aa", False),  # too short
        ("t_28df69728aa2x", False),
        ("tt_28df69728aa2", False),
        ("postgres", False),
        ("chatbot", False),
    ],
)
def test_leftover_cleanup_only_matches_fixture_names(name, matches):
    assert bool(re.match(conftest.TEST_DB_PATTERN, name)) is matches


# ---------- reusable migrated copy (O-006) ----------


@pytest.fixture
def spare_copy(_migrated_template, _reusable_copy):
    """A private clone plus the template's fingerprint."""
    admin = conftest._test_admin_url()
    name = conftest._new_database_name()
    conftest._clone_database(admin, _migrated_template, name)
    yield admin, name, _reusable_copy["fingerprint"]
    conftest._drop_database(admin, name)


def seed(url):
    with psycopg.connect(url, autocommit=True) as conn:
        t = conn.execute(
            "INSERT INTO tenants (slug, name, fallback_text) VALUES ('acme', 'A', 'x') RETURNING id"
        ).fetchone()[0]
        ch = conn.execute(
            "INSERT INTO channels (tenant_id, type) VALUES (%s, 'web') RETURNING id", (t,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO contacts (tenant_id, channel_id, external_user_id) VALUES (%s, %s, 'v')",
            (t, ch),
        )
        conn.execute("INSERT INTO jobs (kind) VALUES ('k')")
        # Saving then deleting a quick answer leaves history rows; a DELETE-based reset
        # would fire the history trigger again and fail on the tenant's foreign key.
        conn.execute(
            "INSERT INTO quick_answers (tenant_id, code, triggers, answers)"
            " VALUES (%s, 'FEES', ARRAY['fees'], '{\"en\": \"Free.\"}')",
            (t,),
        )
        conn.execute("DELETE FROM quick_answers")


def row_counts(url):
    with psycopg.connect(url) as conn:
        tables = [
            r[0]
            for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ]
        return {
            t: conn.execute(
                sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(t))
            ).fetchone()[0]
            for t in tables
        }


def test_reset_empties_every_table_but_keeps_migrations(spare_copy):
    admin, name, fingerprint = spare_copy
    url = conftest._url_for(admin, name)
    seed(url)
    assert conftest._reset_copy(admin, name, fingerprint) is True
    counts = row_counts(url)
    assert counts.pop("schema_version") == 4
    assert set(counts.values()) == {0}
    assert conftest._schema_fingerprint(url) == fingerprint


def test_reset_restarts_ids_like_a_fresh_clone(spare_copy):
    admin, name, fingerprint = spare_copy
    url = conftest._url_for(admin, name)
    seed(url)
    assert conftest._reset_copy(admin, name, fingerprint) is True
    with psycopg.connect(url, autocommit=True) as conn:
        first = conn.execute(
            "INSERT INTO tenants (slug, name, fallback_text) VALUES ('bb', 'B', 'x') RETURNING id"
        ).fetchone()[0]
    assert first == 1


@pytest.mark.parametrize(
    "change",
    [
        "CREATE TABLE extra (id int)",
        "ALTER TABLE tenants ADD COLUMN extra int",
        "ALTER TABLE tenants ALTER COLUMN name DROP NOT NULL",
        "ALTER TABLE contacts DROP CONSTRAINT contacts_status_check",
        "CREATE INDEX extra_idx ON jobs (kind)",
        "ALTER TABLE quick_answers DISABLE TRIGGER quick_answers_history",
        "CREATE FUNCTION extra() RETURNS int LANGUAGE sql AS 'SELECT 1'",
        "CREATE TYPE extra AS ENUM ('a')",
        "CREATE SCHEMA extra",
        "ALTER TABLE jobs ALTER COLUMN kind SET DEFAULT 'x'",
        "DELETE FROM schema_version WHERE name = '003_quick_answers_and_contact_details.sql'",
    ],
)
def test_changed_structure_is_detected_so_the_copy_is_recloned(spare_copy, change):
    admin, name, fingerprint = spare_copy
    url = conftest._url_for(admin, name)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(change)
    assert conftest._reset_copy(admin, name, fingerprint) is False


def test_changed_database_setting_is_detected(spare_copy):
    admin, name, fingerprint = spare_copy
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("ALTER DATABASE {} SET work_mem = '8MB'").format(sql.Identifier(name)))
    assert conftest._reset_copy(admin, name, fingerprint) is False


def test_reset_ends_a_connection_the_test_left_in_a_transaction(spare_copy):
    admin, name, fingerprint = spare_copy
    url = conftest._url_for(admin, name)
    seed(url)
    left_open = psycopg.connect(url)
    left_open.execute("LOCK TABLE tenants IN ACCESS EXCLUSIVE MODE")  # would block the reset
    try:
        assert conftest._reset_copy(admin, name, fingerprint) is True
        with pytest.raises(psycopg.OperationalError):  # the server ended it
            left_open.execute("SELECT 1")
    finally:
        left_open.close()
    assert set(row_counts(url).values()) == {0, 4}


def test_seed_really_fills_history(spare_copy):
    admin, name, _ = spare_copy
    url = conftest._url_for(admin, name)
    seed(url)
    counts = row_counts(url)
    assert counts["quick_answer_history"] == 2  # insert + delete
    assert counts["tenants"] == counts["contacts"] == counts["jobs"] == 1


def test_reused_copy_starts_empty(migrated_db_url):
    # Runs after other tests in this process that used (and filled) the same copy.
    counts = row_counts(migrated_db_url)
    assert counts.pop("schema_version") == 4
    assert set(counts.values()) == {0}
