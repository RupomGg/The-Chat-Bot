import threading
import time

import psycopg
import pytest
from psycopg_pool import PoolTimeout

from app import db
from app.db import DatabaseUnavailable, MigrationError, migrate, open_pool, wait_for_db

# ---------- helpers ----------


def write(directory, files):
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8", newline="")
    return directory


BASE = {
    "000_schema_version.sql": (db.MIGRATIONS_DIR / "000_schema_version.sql").read_text(
        encoding="utf-8"
    ),
    "001_things.sql": "CREATE TABLE things (id int PRIMARY KEY, label text);\n",
    "002_seed.sql": "INSERT INTO things VALUES (1, 'uses table from 001');\n",
}


@pytest.fixture
def mig_dir(tmp_path):
    return write(tmp_path, BASE)


def rows(url, query):
    with psycopg.connect(url) as conn:
        return conn.execute(query).fetchall()


def versions(url):
    return rows(url, "SELECT version, name FROM schema_version ORDER BY version")


def table_exists(url, table):
    return rows(url, f"SELECT to_regclass('{table}') IS NOT NULL")[0][0]


# ---------- applying ----------


def test_fresh_db_applies_all_in_order(db_url, mig_dir):
    applied = migrate(db_url, mig_dir)
    assert applied == ["000_schema_version.sql", "001_things.sql", "002_seed.sql"]
    assert versions(db_url) == [
        (0, "000_schema_version.sql"),
        (1, "001_things.sql"),
        (2, "002_seed.sql"),
    ]
    assert rows(db_url, "SELECT label FROM things") == [("uses table from 001",)]


def test_rerun_applies_nothing(db_url, mig_dir):
    migrate(db_url, mig_dir)
    assert migrate(db_url, mig_dir) == []
    assert rows(db_url, "SELECT count(*) FROM things") == [(1,)]  # seed not inserted twice


def test_new_migration_added_later_is_applied_alone(db_url, mig_dir):
    migrate(db_url, mig_dir)
    write(mig_dir, {"003_more.sql": "ALTER TABLE things ADD COLUMN note text;"})
    assert migrate(db_url, mig_dir) == ["003_more.sql"]


def test_real_migrations_directory_applies(db_url):
    assert migrate(db_url) == [
        "000_schema_version.sql",
        "001_init.sql",
        "002_universal_core.sql",
    ]
    cols = rows(
        db_url,
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = 'schema_version' ORDER BY ordinal_position",
    )
    assert cols == [
        ("version", "integer"),
        ("name", "text"),
        ("checksum", "text"),
        ("applied_at", "timestamp with time zone"),
    ]


def test_percent_signs_in_sql_are_not_treated_as_placeholders(db_url, mig_dir):
    write(mig_dir, {"003_pct.sql": "INSERT INTO things VALUES (2, '100% sure %s');"})
    migrate(db_url, mig_dir)
    assert rows(db_url, "SELECT label FROM things WHERE id = 2") == [("100% sure %s",)]


# ---------- failures roll back ----------


def test_failing_migration_rolls_back_only_itself(db_url, mig_dir):
    write(
        mig_dir,
        {"003_broken.sql": "CREATE TABLE half_done (id int);\nSELECT * FROM no_such_table;\n"},
    )
    with pytest.raises(MigrationError, match="003_broken.sql failed"):
        migrate(db_url, mig_dir)
    assert not table_exists(db_url, "half_done")  # the part before the error was undone
    assert [v for v, _ in versions(db_url)] == [0, 1, 2]  # earlier ones kept


def test_fix_after_failure_then_succeeds(db_url, mig_dir):
    write(mig_dir, {"003_broken.sql": "SELECT * FROM no_such_table;"})
    with pytest.raises(MigrationError):
        migrate(db_url, mig_dir)
    write(mig_dir, {"003_broken.sql": "CREATE TABLE fixed (id int);"})
    assert migrate(db_url, mig_dir) == ["003_broken.sql"]


def test_zero_migration_that_does_not_create_schema_version_fails(db_url, tmp_path):
    write(tmp_path, {"000_wrong.sql": "CREATE TABLE something_else (id int);"})
    with pytest.raises(MigrationError, match="000_wrong.sql failed"):
        migrate(db_url, tmp_path)
    assert not table_exists(db_url, "something_else")


# ---------- edits after applying ----------


def test_edited_applied_migration_is_refused(db_url, mig_dir):
    migrate(db_url, mig_dir)
    write(mig_dir, {"001_things.sql": "CREATE TABLE things (id int PRIMARY KEY);\n"})
    with pytest.raises(MigrationError, match="001_things.sql was changed after it was applied"):
        migrate(db_url, mig_dir)


def test_line_ending_change_is_not_an_edit(db_url, mig_dir):
    migrate(db_url, mig_dir)
    crlf = BASE["001_things.sql"].replace("\n", "\r\n")
    write(mig_dir, {"001_things.sql": crlf})  # e.g. git checkout on Windows
    assert migrate(db_url, mig_dir) == []


def test_renamed_applied_migration_is_refused(db_url, mig_dir):
    migrate(db_url, mig_dir)
    (mig_dir / "001_things.sql").rename(mig_dir / "001_items.sql")
    with pytest.raises(MigrationError, match="001_items.sql.*001_things.sql"):
        migrate(db_url, mig_dir)


def test_deleted_applied_migration_is_refused(db_url, mig_dir):
    migrate(db_url, mig_dir)
    (mig_dir / "002_seed.sql").unlink()
    with pytest.raises(MigrationError, match="002_seed.sql was applied but its file is missing"):
        migrate(db_url, mig_dir)


# ---------- file checks (nothing touches the database) ----------


@pytest.mark.parametrize(
    "files, message",
    [
        ({}, "no migrations found"),
        ({"000_a.sql": "SELECT 1;", "002_b.sql": "SELECT 1;"}, "no gaps or duplicates"),
        ({"000_a.sql": "SELECT 1;", "000_b.sql": "SELECT 1;"}, "no gaps or duplicates"),
        ({"001_a.sql": "SELECT 1;"}, "no gaps or duplicates"),
        ({"0_init.sql": "SELECT 1;"}, "bad migration file name: 0_init.sql"),
        ({"000-init.sql": "SELECT 1;"}, "bad migration file name: 000-init.sql"),
        ({"000_Init.sql": "SELECT 1;"}, "bad migration file name: 000_Init.sql"),
        ({"000_init.SQL": "SELECT 1;"}, "bad migration file name: 000_init.SQL"),
        ({"000_init sql.sql": "SELECT 1;"}, "bad migration file name"),
        ({"000_empty.sql": "   \n\t\n"}, "000_empty.sql: contains no SQL"),
        ({"000_comments.sql": "-- only a comment\n  -- another\n"}, "contains no SQL"),
    ],
)
def test_bad_migration_files_refused_before_touching_db(tmp_path, files, message):
    write(tmp_path, files)
    with pytest.raises(MigrationError, match=message):
        migrate("postgresql://never-used@invalid.invalid/none", tmp_path)


def test_non_utf8_file_refused(tmp_path):
    (tmp_path / "000_bad.sql").write_bytes(b"SELECT '\xff\xfe';")
    with pytest.raises(MigrationError, match="000_bad.sql: not valid UTF-8"):
        migrate("postgresql://never-used@invalid.invalid/none", tmp_path)


def test_non_sql_files_and_folders_are_ignored(db_url, mig_dir):
    write(mig_dir, {"README.md": "notes", "notes.txt": "x"})
    (mig_dir / "old.sql").mkdir()  # a folder, even one ending in .sql
    assert len(migrate(db_url, mig_dir)) == 3


# ---------- concurrency ----------


def test_two_instances_starting_together_apply_once(db_url, mig_dir):
    write(mig_dir, {"001_things.sql": "SELECT pg_sleep(0.5);\n" + BASE["001_things.sql"]})
    results, errors = [], []

    def run():
        try:
            results.append(migrate(db_url, mig_dir))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    assert sorted(len(r) for r in results) == [0, 3]  # one applied all, the other nothing
    assert [v for v, _ in versions(db_url)] == [0, 1, 2]


def test_lock_is_released_after_failure(db_url, mig_dir):
    write(mig_dir, {"003_broken.sql": "SELECT * FROM no_such_table;"})
    with pytest.raises(MigrationError):
        migrate(db_url, mig_dir)
    with psycopg.connect(db_url) as conn:
        got = conn.execute("SELECT pg_try_advisory_lock(%s)", (db.LOCK_KEY,)).fetchone()[0]
    assert got is True


# ---------- waiting for the database ----------


def refusing_connect(message):
    def connect(url, **kwargs):
        raise psycopg.OperationalError(message)

    return connect


def test_wait_for_db_succeeds_immediately(db_url):
    sleeps = []
    wait_for_db(db_url, sleep=sleeps.append)
    assert sleeps == []


def test_wait_for_db_retries_then_succeeds(db_url):
    calls, sleeps = [], []

    def flaky(url, **kwargs):
        calls.append(kwargs)
        if len(calls) < 3:
            raise psycopg.OperationalError("not yet")
        return psycopg.connect(url, **kwargs)

    wait_for_db(db_url, sleep=sleeps.append, connect=flaky)
    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]
    assert all(k["connect_timeout"] == 5 for k in calls)


def test_wait_for_db_gives_up_with_bounded_backoff():
    sleeps = []
    with pytest.raises(DatabaseUnavailable, match="unreachable after 6 attempts"):
        wait_for_db(
            "postgresql://u:pw@h/db", sleep=sleeps.append, connect=refusing_connect("refused")
        )
    assert sleeps == [0.5, 1.0, 2.0, 4.0, 8.0]  # doubling, capped, no sleep after the last try
    assert sum(sleeps) <= 16


def test_wait_for_db_error_never_contains_password():
    url = "postgresql://bot:S3cret-Pw@db.example.com/app"
    with pytest.raises(DatabaseUnavailable) as exc:
        wait_for_db(
            url,
            attempts=1,
            sleep=lambda s: None,
            connect=refusing_connect("failed for postgresql://bot:S3cret-Pw@db\nsecond line"),
        )
    assert "S3cret-Pw" not in str(exc.value)
    assert "***" in str(exc.value)
    assert "second line" not in str(exc.value)


def test_wait_for_db_error_with_empty_message_uses_error_type():
    with pytest.raises(DatabaseUnavailable, match="OperationalError"):
        wait_for_db("postgresql://h/db", attempts=1, connect=refusing_connect(""))


def test_wait_for_db_url_without_password():
    with pytest.raises(DatabaseUnavailable, match="refused here"):
        wait_for_db("postgresql://h/db", attempts=1, connect=refusing_connect("refused here"))


def test_wait_for_db_against_a_closed_port_is_bounded():
    # A real refused connection: each attempt is capped by CONNECT_TIMEOUT (Windows waits for
    # it in full; Linux refuses instantly). Worst case at startup: 6 × 5 s + 15.5 s of pauses.
    start = time.monotonic()
    with pytest.raises(DatabaseUnavailable):
        wait_for_db("postgresql://u:p@127.0.0.1:1/db", attempts=1)
    assert time.monotonic() - start < db.CONNECT_TIMEOUT + 3


# ---------- pool ----------


def test_pool_gives_working_connections(db_url):
    pool = open_pool(db_url)
    try:
        with pool.connection() as conn:
            assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        pool.close()


def test_short_borrow_timeout_does_not_limit_opening(db_url, monkeypatch):
    # Regression (G7 flake in P1.2): open_pool used the borrow timeout to wait for the first
    # connection too, so a slow first connect (Windows under load) failed pool opening.
    real_connect = psycopg.Connection.connect.__func__

    def slow_connect(cls, *args, **kwargs):
        time.sleep(0.5)  # slower than the borrow timeout below
        return real_connect(cls, *args, **kwargs)

    monkeypatch.setattr(psycopg.Connection, "connect", classmethod(slow_connect))
    pool = open_pool(db_url, max_size=1, timeout=0.1)
    try:
        with pool.connection(timeout=2) as conn:
            assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        pool.close()


def test_pool_open_fails_cleanly_when_database_is_gone():
    # Worst case: open_timeout, then close() waits for a worker's connect attempt, which
    # connect_timeout caps (Windows waits it out on a refused port; Linux refuses at once).
    start = time.monotonic()
    with pytest.raises(PoolTimeout):
        open_pool("postgresql://u:p@127.0.0.1:1/db", open_timeout=0.5)
    assert time.monotonic() - start < 0.5 + db.CONNECT_TIMEOUT + 3


def test_pool_connections_have_a_connect_timeout(db_url):
    pool = open_pool(db_url)
    try:
        with pool.connection() as conn:
            assert f"connect_timeout={db.CONNECT_TIMEOUT}" in conn.info.dsn
    finally:
        pool.close()


def test_exhausted_pool_times_out_cleanly(db_url):
    pool = open_pool(db_url, max_size=1, timeout=0.3)
    try:
        with pool.connection():
            start = time.monotonic()
            with pytest.raises(PoolTimeout), pool.connection():
                pass  # never reached: the pool is exhausted
            assert time.monotonic() - start < 2
        with pool.connection() as conn:  # usable again once the first is returned
            assert conn.execute("SELECT 1").fetchone() == (1,)
    finally:
        pool.close()
