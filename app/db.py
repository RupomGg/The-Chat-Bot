"""Database access: wait for the server, apply migrations, open the connection pool.

Synchronous psycopg (D-009). Migrations are files named NNN_lowercase_name.sql in
migrations/, numbered 000, 001, 002, ... Each runs in its own transaction together with
its schema_version row, so a failed file leaves no trace. Applied files must never be
edited: a checksum check refuses to start if one was.
"""

import hashlib
import re
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg_pool import ConnectionPool

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
MIGRATION_NAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
LOCK_KEY = 7_345_901_223  # advisory lock id shared by every app instance
POOL_MAX_SIZE = 10
POOL_TIMEOUT = 10.0  # seconds to wait for a free connection before failing
CONNECT_TIMEOUT = 5  # seconds per connection attempt
POOL_OPEN_TIMEOUT = 2 * CONNECT_TIMEOUT  # seconds for the pool's first connection at startup


class DatabaseUnavailable(Exception):
    """The database could not be reached at startup."""


class MigrationError(Exception):
    """A migration file is invalid, failed, or no longer matches what was applied."""


def _first_line_without_password(error: Exception, url: str) -> str:
    message = (str(error).strip().splitlines() or [type(error).__name__])[0]
    password = urlsplit(url).password
    return message.replace(password, "***") if password else message


def wait_for_db(
    url: str,
    attempts: int = 6,
    first_delay: float = 0.5,
    max_delay: float = 8.0,
    sleep: Callable[[float], None] = time.sleep,
    connect: Callable[..., psycopg.Connection] = psycopg.connect,
) -> None:
    """Try to connect, doubling the pause between tries. Total pause ≤ 15.5 s by default."""
    delay = first_delay
    for attempt in range(1, attempts + 1):
        try:
            with connect(url, connect_timeout=CONNECT_TIMEOUT):
                return
        except psycopg.OperationalError as err:
            last_error = err
        if attempt < attempts:
            sleep(delay)
            delay = min(delay * 2, max_delay)
    reason = _first_line_without_password(last_error, url)
    raise DatabaseUnavailable(f"database unreachable after {attempts} attempts: {reason}")


def _has_sql(text: str) -> bool:
    return any(line.strip() and not line.strip().startswith("--") for line in text.splitlines())


def _load_migrations(directory: Path) -> list[tuple[int, str, str, str]]:
    """Read and check every migration file before touching the database."""
    files = sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == ".sql")
    if not files:
        raise MigrationError(f"no migrations found in {directory}")
    migrations = []
    for path in files:
        match = MIGRATION_NAME.match(path.name)
        if not match:
            raise MigrationError(
                f"bad migration file name: {path.name} (expected NNN_lowercase_name.sql)"
            )
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as err:
            raise MigrationError(f"{path.name}: not valid UTF-8") from err
        text = text.replace("\r\n", "\n")  # same checksum on Windows and Linux checkouts
        if not _has_sql(text):
            raise MigrationError(f"{path.name}: contains no SQL")
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        migrations.append((int(match[1]), path.name, text, checksum))
    if [version for version, *_ in migrations] != list(range(len(migrations))):
        names = ", ".join(name for _, name, _, _ in migrations)
        raise MigrationError(
            f"migration numbers must be 000, 001, 002, ... with no gaps or duplicates: {names}"
        )
    return migrations


def _applied(conn: psycopg.Connection) -> dict[int, tuple[str, str]]:
    if conn.execute("SELECT to_regclass('schema_version')").fetchone()[0] is None:
        return {}
    return {
        version: (name, checksum)
        for version, name, checksum in conn.execute(
            "SELECT version, name, checksum FROM schema_version"
        )
    }


def migrate(url: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations in order. Returns the names applied by this call."""
    migrations = _load_migrations(directory)
    applied_now = []
    with psycopg.connect(url, autocommit=True, connect_timeout=CONNECT_TIMEOUT) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))  # one instance at a time
        try:
            done = _applied(conn)
            on_disk = {version for version, *_ in migrations}
            for version in sorted(set(done) - on_disk):
                raise MigrationError(f"{done[version][0]} was applied but its file is missing")
            for version, name, text, checksum in migrations:
                if version in done:
                    done_name, done_checksum = done[version]
                    if done_name != name:
                        raise MigrationError(
                            f"{name} has the number of already-applied {done_name}; "
                            "applied files must not be renamed"
                        )
                    if done_checksum != checksum:
                        raise MigrationError(
                            f"{name} was changed after it was applied; add a new migration instead"
                        )
                    continue
                try:
                    with conn.transaction():
                        conn.execute(text)
                        conn.execute(
                            "INSERT INTO schema_version (version, name, checksum)"
                            " VALUES (%s, %s, %s)",
                            (version, name, checksum),
                        )
                except psycopg.Error as err:
                    reason = _first_line_without_password(err, url)
                    raise MigrationError(f"{name} failed: {reason}") from err
                applied_now.append(name)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    return applied_now


def open_pool(
    url: str,
    max_size: int = POOL_MAX_SIZE,
    timeout: float = POOL_TIMEOUT,
    open_timeout: float = POOL_OPEN_TIMEOUT,
) -> ConnectionPool:
    """A ready pool.

    `timeout`: how long borrowing a connection waits before PoolTimeout.
    `open_timeout`: how long opening may take to make its first connection. Kept separate:
    a short borrow timeout must not make startup fail on a slow first connect.
    """
    pool = ConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        timeout=timeout,
        kwargs={"connect_timeout": CONNECT_TIMEOUT},  # a hung network can't stall a worker
        open=False,
    )
    pool.open(wait=True, timeout=open_timeout)
    return pool
