import os
import pathlib
import time
import uuid
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from hypothesis import settings
from psycopg import sql

from app.config import load_config
from app.db import migrate
from app.main import create_app

# Hypothesis (D-004): same inputs every run so the gate is stable (G7); no per-example deadline
# on slow machines; at most 500 examples per property test.
settings.register_profile("gate", derandomize=True, deadline=None, max_examples=500)
settings.load_profile("gate")

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEST_DB_PATTERN = r"^t_[0-9a-f]{12}$"  # only databases these fixtures create
SESSION_LOCK_KEY = 7_345_901_224  # held by the one test run allowed to clean up leftovers
OWN_DATABASES: set[str] = set()  # databases created by this run; cleanup never touches them


def _test_admin_url() -> str:
    """TEST_DATABASE_URL from the environment (CI) or the local .env file."""
    url = os.environ.get("TEST_DATABASE_URL", "")
    env_file = ROOT / ".env"
    if not url and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "TEST_DATABASE_URL":
                url = value.strip()
    if not url:
        raise RuntimeError("TEST_DATABASE_URL is not set (see INSTRUCTION.md §5.1)")
    return url


def _run_retrying(admin: str, statement: sql.Composed, retry_for: float) -> None:
    """Run one statement, retrying briefly while an autovacuum worker is in the way.

    Autovacuum runs as a superuser and may connect to any database at any moment. Our
    non-superuser test role can't end it, so DROP ... WITH (FORCE) fails with
    InsufficientPrivilege, and CREATE ... TEMPLATE fails with ObjectInUse while it's
    connected to the template. The worker finishes in milliseconds; retry for a few
    seconds, then fail loudly.
    """
    deadline = time.monotonic() + retry_for
    while True:
        try:
            with psycopg.connect(admin, autocommit=True) as conn:
                conn.execute(statement)
            return
        except (psycopg.errors.InsufficientPrivilege, psycopg.errors.ObjectInUse):
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)


def _drop_database(admin: str, name: str, retry_for: float = 5.0) -> None:
    statement = sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
    _run_retrying(admin, statement, retry_for)


def _clone_database(admin: str, template: str, name: str, retry_for: float = 5.0) -> None:
    statement = sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
        sql.Identifier(name), sql.Identifier(template)
    )
    _run_retrying(admin, statement, retry_for)


def _url_for(admin: str, name: str) -> str:
    return urlunsplit(urlsplit(admin)._replace(path="/" + name))


def _new_database_name() -> str:
    name = "t_" + uuid.uuid4().hex[:12]
    OWN_DATABASES.add(name)
    return name


def _create_database(admin: str, name: str) -> None:
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def _try_session_lock(admin: str, key: int = SESSION_LOCK_KEY) -> psycopg.Connection | None:
    """Hold `key` for this whole test run. None means another run holds it right now."""
    conn = psycopg.connect(admin, autocommit=True)
    if conn.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone()[0]:
        return conn
    conn.close()
    return None


def _leftovers(admin: str, own: set[str]) -> list[str]:
    """Test databases from earlier runs: fixture-made names that this run didn't create."""
    with psycopg.connect(admin, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT datname FROM pg_database WHERE datname ~ %s ORDER BY datname",
            (TEST_DB_PATTERN,),
        )
        return [name for (name,) in rows if name not in own]


def pytest_configure(config):
    """Drop leftovers of crashed runs, but only when no other test run is active.

    Two runs at once (e.g. the owner and Claude) must not delete each other's databases.
    The run holding the lock is the only one running, so its cleanup is safe; a run that
    can't get the lock skips cleanup (leftovers just wait for the next solo run).

    Runs only in the main pytest process, before any parallel (xdist) worker starts, so a
    worker can never drop a database another worker is using. The lock is held until the
    whole run ends.
    """
    if hasattr(config, "workerinput"):  # an xdist worker: the main process did this
        return
    admin = _test_admin_url()
    config._session_lock = _try_session_lock(admin)
    if config._session_lock is not None:
        for name in _leftovers(admin, OWN_DATABASES):
            _drop_database(admin, name)


def pytest_unconfigure(config):
    lock = getattr(config, "_session_lock", None)
    if lock is not None:
        lock.close()  # releases the advisory lock


@pytest.fixture
def db_url():
    """A brand-new empty database for one test, dropped afterwards."""
    admin = _test_admin_url()
    name = _new_database_name()
    _create_database(admin, name)
    yield _url_for(admin, name)
    _drop_database(admin, name)


@pytest.fixture(scope="session")
def _migrated_template():
    """One database with every migration applied, copied by `migrated_db_url`."""
    admin = _test_admin_url()
    name = _new_database_name()
    _create_database(admin, name)
    migrate(_url_for(admin, name))
    yield name
    _drop_database(admin, name)


# Everything a test could change in a database's structure. Two databases with the same
# fingerprint have the same tables, columns, defaults, constraints, indexes, triggers,
# functions, types, permissions, database settings and applied migrations.
SCHEMA_FINGERPRINT = """
WITH ns AS (
    SELECT oid FROM pg_namespace
    WHERE nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
      AND nspname NOT LIKE 'pg_temp%' AND nspname NOT LIKE 'pg_toast_temp%'
)
SELECT md5(string_agg(item, E'\n' ORDER BY item)) FROM (
    SELECT concat_ws(' ', 'ns', nspname, nspacl)
    FROM pg_namespace WHERE oid IN (SELECT oid FROM ns)
    UNION ALL
    SELECT concat_ws(' ', 'rel', oid::regclass, relkind, relrowsecurity, relacl, reloptions)
    FROM pg_class WHERE relnamespace IN (SELECT oid FROM ns)
    UNION ALL
    SELECT concat_ws(' ', 'col', a.attrelid::regclass, a.attname,
        format_type(a.atttypid, a.atttypmod), a.attnotnull, a.attidentity, a.attgenerated,
        pg_get_expr(d.adbin, d.adrelid))
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
    WHERE c.relnamespace IN (SELECT oid FROM ns) AND a.attnum > 0 AND NOT a.attisdropped
    UNION ALL
    SELECT concat_ws(' ', 'con', conrelid::regclass, contypid::regtype, conname,
        pg_get_constraintdef(oid))
    FROM pg_constraint WHERE connamespace IN (SELECT oid FROM ns)
    UNION ALL
    SELECT concat_ws(' ', 'idx', pg_get_indexdef(i.indexrelid))
    FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
    WHERE c.relnamespace IN (SELECT oid FROM ns)
    UNION ALL
    SELECT concat_ws(' ', 'trg', pg_get_triggerdef(oid), tgenabled)
    FROM pg_trigger WHERE NOT tgisinternal
    UNION ALL
    SELECT concat_ws(' ', 'fn', oid::regprocedure, prokind, md5(prosrc), proconfig, proacl)
    FROM pg_proc WHERE pronamespace IN (SELECT oid FROM ns)
    UNION ALL
    SELECT concat_ws(' ', 'type', oid::regtype, typtype)
    FROM pg_type WHERE typnamespace IN (SELECT oid FROM ns)
    UNION ALL
    SELECT concat_ws(' ', 'enum', enumtypid::regtype, enumsortorder, enumlabel) FROM pg_enum
    UNION ALL
    SELECT concat_ws(' ', 'ext', extname, extversion) FROM pg_extension
    UNION ALL
    SELECT concat_ws(' ', 'dbset', setrole, setconfig) FROM pg_db_role_setting
    WHERE setdatabase = (SELECT oid FROM pg_database WHERE datname = current_database())
    UNION ALL
    SELECT concat_ws(' ', 'db', datacl) FROM pg_database WHERE datname = current_database()
    UNION ALL
    SELECT concat_ws(' ', 'ran', s) FROM schema_version s
) AS everything(item)
"""

USER_TABLES = """
SELECT c.oid::regclass::text FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND c.relname <> 'schema_version'
ORDER BY 1
"""


def _schema_fingerprint(url: str) -> str:
    with psycopg.connect(url) as conn:
        return conn.execute(SCHEMA_FINGERPRINT).fetchone()[0]


def _end_other_sessions(admin: str, name: str) -> None:
    """End connections a test left open to `name` (same role, so no superuser needed)."""
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity"
            " WHERE datname = %s AND usename = current_user AND pid <> pg_backend_pid()",
            (name,),
        )


def _reset_copy(admin: str, name: str, fingerprint: str) -> bool:
    """Put a used copy back to the template's state. False: the structure changed, re-clone.

    Empties every table except the applied-migrations list and restarts every sequence.
    TRUNCATE, not DELETE: DELETE fires triggers (quick-answer history would refill itself).
    """
    _end_other_sessions(admin, name)
    url = _url_for(admin, name)
    if _schema_fingerprint(url) != fingerprint:
        return False
    with psycopg.connect(url) as conn:
        tables = [sql.SQL(t) for (t,) in conn.execute(USER_TABLES)]  # already-quoted regclass
        conn.execute(sql.SQL("TRUNCATE {} RESTART IDENTITY").format(sql.SQL(", ").join(tables)))
        conn.execute(
            "SELECT setval(format('%I.%I', schemaname, sequencename), start_value, false)"
            " FROM pg_sequences WHERE last_value IS NOT NULL"
        )
    return True


@pytest.fixture(scope="session")
def _reusable_copy(_migrated_template):
    """One copy of the template per test process, reset after each test instead of
    dropped and re-cloned (each clone + drop costs seconds on a slow disk; O-006)."""
    admin = _test_admin_url()
    state = {"name": None, "fingerprint": _schema_fingerprint(_url_for(admin, _migrated_template))}
    yield state
    if state["name"] is not None:
        _drop_database(admin, state["name"])


@pytest.fixture
def migrated_db_url(_migrated_template, _reusable_copy):
    """A database in exactly the fully migrated template's state, for one test.

    Reused between tests: afterwards its tables are emptied and sequences restarted. If the
    test changed its structure (fingerprint differs) or the reset fails, it is dropped and
    the next test gets a fresh clone.
    """
    admin = _test_admin_url()
    copy = _reusable_copy
    if copy["name"] is None:
        copy["name"] = _new_database_name()
        _clone_database(admin, _migrated_template, copy["name"])
    yield _url_for(admin, copy["name"])
    reset = False
    try:
        reset = _reset_copy(admin, copy["name"], copy["fingerprint"])
    finally:
        if not reset:
            _drop_database(admin, copy["name"])
            copy["name"] = None


@pytest.fixture
def env_vars(db_url):
    return {
        "ENV": "test",
        "DATABASE_URL": db_url,
        "FERNET_KEY": Fernet.generate_key().decode(),
        "SESSION_SECRET": "t" * 40,
        "PUBLIC_BASE_URL": "https://bot.example.com",
    }


@pytest.fixture
def config(env_vars):
    return load_config(env_vars)


@pytest.fixture
def client(config):
    with TestClient(create_app(config)) as c:
        yield c
