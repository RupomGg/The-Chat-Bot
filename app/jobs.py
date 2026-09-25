"""Postgres job queue (PRD §8): durable, retried, never processed twice at the same time.

Every incoming message becomes a job; a worker (app/worker.py) claims it with
FOR UPDATE SKIP LOCKED, so two workers never take the same job. The claim time is the
job's lock token: if a worker dies mid-job the lock goes stale and another worker takes
the job over, and the first worker (if it wakes up) can no longer finish or fail it.
All times come from the database clock, so every worker agrees on them.
"""

import datetime
import json
from dataclasses import dataclass

from psycopg.types.json import Jsonb

BACKOFF_BASE = datetime.timedelta(seconds=30)  # 30 s, 1 min, 2 min, 4 min, 8 min …
BACKOFF_MAX = datetime.timedelta(hours=1)
LOCK_TIMEOUT = datetime.timedelta(minutes=5)  # a job running longer is taken over
MAX_ERROR_CHARS = 2000


class JobError(ValueError):
    """The job can't be queued; the message says why."""


@dataclass(frozen=True)
class Job:
    id: int
    kind: str
    payload: dict
    attempts: int  # including this one
    max_attempts: int
    locked_at: datetime.datetime  # this claim's token


def backoff(attempts: int) -> datetime.timedelta:
    """Wait before the next try after `attempts` failed tries: doubles, capped at 1 hour."""
    return min(BACKOFF_BASE * 2 ** (attempts - 1), BACKOFF_MAX)


def enqueue(conn, kind, payload=None, *, delay=None, max_attempts=6) -> int:
    """Queue a job to run now (or after `delay`). Returns its id."""
    if not isinstance(kind, str) or not kind.strip():
        raise JobError("kind must be non-empty text")
    payload = {} if payload is None else payload
    if not isinstance(payload, dict):
        raise JobError("payload must be a dict")
    try:
        json.dumps(payload, allow_nan=False)  # the database stores it as JSON
    except (TypeError, ValueError) as error:
        raise JobError(f"payload is not JSON: {error}") from None
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
        raise JobError("max_attempts must be a whole number of at least 1")
    delay = delay or datetime.timedelta(0)
    if not isinstance(delay, datetime.timedelta) or delay < datetime.timedelta(0):
        raise JobError("delay must be a non-negative timedelta")
    with conn.transaction():
        return conn.execute(
            "INSERT INTO jobs (kind, payload, run_at, max_attempts)"
            " VALUES (%s, %s, now() + %s, %s) RETURNING id",
            (kind.strip(), Jsonb(payload), delay, max_attempts),
        ).fetchone()[0]


CLAIM = """
UPDATE jobs SET status = 'running', locked_at = clock_timestamp(), attempts = attempts + 1
WHERE id = (
    SELECT id FROM jobs
    WHERE attempts < max_attempts
      AND ((status = 'pending' AND run_at <= now())
           OR (status = 'running' AND locked_at < now() - %s))
    ORDER BY run_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING id, kind, payload, attempts, max_attempts, locked_at
"""


def claim(conn, *, lock_timeout=LOCK_TIMEOUT) -> Job | None:
    """Take the next due job (or one whose worker stopped), or None if nothing is due."""
    with conn.transaction():
        row = conn.execute(CLAIM, (lock_timeout,)).fetchone()
    return None if row is None else Job(*row)


def bury_abandoned(conn, *, lock_timeout=LOCK_TIMEOUT) -> list[Job]:
    """Jobs whose worker stopped during their last allowed attempt: nobody can retry them,
    so they're marked dead. Returns them so the caller can alert."""
    with conn.transaction():
        rows = conn.execute(
            "UPDATE jobs SET status = 'dead', locked_at = NULL,"
            " last_error = 'worker stopped during the last attempt'"
            " WHERE status = 'running' AND attempts >= max_attempts AND locked_at < now() - %s"
            " RETURNING id, kind, payload, attempts, max_attempts, locked_at",
            (lock_timeout,),
        ).fetchall()
    return [Job(*row) for row in rows]


def complete(conn, job: Job) -> bool:
    """Mark done. False if the job was taken over meanwhile (its lock went stale)."""
    with conn.transaction():
        row = conn.execute(
            "UPDATE jobs SET status = 'done', locked_at = NULL, last_error = NULL"
            " WHERE id = %s AND status = 'running' AND locked_at = %s RETURNING id",
            (job.id, job.locked_at),
        ).fetchone()
    return row is not None


def fail(conn, job: Job, error: str, *, retry=True) -> str | None:
    """Record a failure: back to 'pending' after a backoff, or 'dead' when attempts are used
    up (or retry=False). Returns the new status, or None if the job was taken over."""
    dead = not retry or job.attempts >= job.max_attempts
    with conn.transaction():
        row = conn.execute(
            "UPDATE jobs SET status = %s, locked_at = NULL, last_error = %s,"
            " run_at = CASE WHEN %s THEN run_at ELSE now() + %s END"
            " WHERE id = %s AND status = 'running' AND locked_at = %s RETURNING status",
            (
                "dead" if dead else "pending",
                str(error)[:MAX_ERROR_CHARS],
                dead,
                backoff(job.attempts),
                job.id,
                job.locked_at,
            ),
        ).fetchone()
    return None if row is None else row[0]


def queue_stats(conn) -> dict:
    """For /healthz: jobs due now, how long the oldest has waited, and dead jobs."""
    depth, oldest, dead = conn.execute(
        "SELECT count(*) FILTER (WHERE status = 'pending' AND run_at <= now()),"
        " coalesce(extract(epoch FROM now() - min(run_at)"
        "   FILTER (WHERE status = 'pending' AND run_at <= now())), 0),"
        " count(*) FILTER (WHERE status = 'dead')"
        " FROM jobs"
    ).fetchone()
    return {"depth": depth, "oldest_age_seconds": round(float(oldest), 1), "dead": dead}
