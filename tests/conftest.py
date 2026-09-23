import os
import pathlib
import time
import uuid
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from psycopg import sql

from app.config import load_config
from app.db import migrate
from app.main import create_app

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


@pytest.fixture(scope="session", autouse=True)
def _session_lock():
    """Drop leftovers of crashed runs, but only when no other test run is active.

    Two runs at once (e.g. the owner and Claude) must not delete each other's databases.
    The run holding the lock is the only one running, so its cleanup is safe; a run that
    can't get the lock skips cleanup (leftovers just wait for the next solo run).
    """
    admin = _test_admin_url()
    lock = _try_session_lock(admin)
    if lock is not None:
        for name in _leftovers(admin, OWN_DATABASES):
            _drop_database(admin, name)
    yield lock
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
def _migrated_template(_session_lock):
    """One database with every migration applied, copied by `migrated_db_url`."""
    admin = _test_admin_url()
    name = _new_database_name()
    _create_database(admin, name)
    migrate(_url_for(admin, name))
    yield name
    _drop_database(admin, name)


@pytest.fixture
def migrated_db_url(_migrated_template):
    """A fresh copy of the fully migrated template for one test, dropped afterwards."""
    admin = _test_admin_url()
    name = _new_database_name()
    _clone_database(admin, _migrated_template, name)
    yield _url_for(admin, name)
    _drop_database(admin, name)


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
