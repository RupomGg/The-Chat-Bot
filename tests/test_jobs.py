"""Job queue and worker (P3.1, PRD §8)."""

import datetime
import logging
import signal
import threading
import time

import psycopg
import pytest

from app import db, jobs, worker
from app.config import load_config
from app.jobs import JobError, backoff, bury_abandoned, claim, complete, enqueue, fail, queue_stats
from app.worker import Worker, main

MINUTE = datetime.timedelta(minutes=1)


@pytest.fixture
def conn(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as c:
        yield c


def row(conn, job_id):
    return conn.execute(
        "SELECT status, attempts, last_error, locked_at IS NOT NULL,"
        " extract(epoch FROM run_at - now()) FROM jobs WHERE id = %s",
        (job_id,),
    ).fetchone()


def make_due(conn, job_id):
    """Skip the backoff wait (tests don't sleep)."""
    conn.execute("UPDATE jobs SET run_at = now() - interval '1 second' WHERE id = %s", (job_id,))


def go_stale(conn, job_id):
    """As if the worker holding this job stopped 10 minutes ago."""
    conn.execute(
        "UPDATE jobs SET locked_at = now() - interval '10 minutes' WHERE id = %s", (job_id,)
    )


# ---------- enqueue ----------


def test_enqueue_stores_a_pending_job(conn):
    job_id = enqueue(conn, " reply ", {"conversation_id": 5})
    status, attempts, error, locked, wait = row(conn, job_id)
    assert (status, attempts, error, locked) == ("pending", 0, None, False)
    assert wait <= 0
    assert conn.execute("SELECT kind, payload FROM jobs").fetchone() == (
        "reply",
        {"conversation_id": 5},
    )


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"kind": ""}, "kind must be non-empty text"),
        ({"kind": "  "}, "kind must be non-empty text"),
        ({"kind": None}, "kind must be non-empty text"),
        ({"payload": ["x"]}, "payload must be a dict"),
        ({"payload": {"x": object()}}, "payload is not JSON"),
        ({"payload": {"x": {1, 2}}}, "payload is not JSON"),
        ({"payload": {"x": float("nan")}}, "payload is not JSON"),
        ({"max_attempts": 0}, "max_attempts must be"),
        ({"max_attempts": True}, "max_attempts must be"),
        ({"max_attempts": "3"}, "max_attempts must be"),
        ({"delay": -MINUTE}, "delay must be"),
        ({"delay": 60}, "delay must be"),
    ],
)
def test_enqueue_rejects_bad_jobs(conn, kwargs, message):
    args = {"kind": "reply", "payload": {}} | kwargs
    with pytest.raises(JobError, match=message):
        enqueue(conn, args.pop("kind"), args.pop("payload"), **args)
    assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


# ---------- claim ----------


def test_claim_takes_a_due_job(conn):
    job_id = enqueue(conn, "reply", {"a": 1})
    job = claim(conn)
    assert (job.id, job.kind, job.payload, job.attempts, job.max_attempts) == (
        job_id,
        "reply",
        {"a": 1},
        1,
        6,
    )
    assert row(conn, job_id)[:2] == ("running", 1)


def test_nothing_due_means_none(conn):
    assert claim(conn) is None


def test_future_job_is_not_picked_early(conn):
    job_id = enqueue(conn, "reminder", delay=datetime.timedelta(hours=1))
    assert claim(conn) is None
    make_due(conn, job_id)
    assert claim(conn).id == job_id


def test_oldest_due_job_first(conn):
    first, second = enqueue(conn, "a"), enqueue(conn, "b")
    conn.execute("UPDATE jobs SET run_at = now() - interval '1 hour' WHERE id = %s", (second,))
    assert [claim(conn).id, claim(conn).id] == [second, first]


def test_a_running_job_is_not_claimed_again(conn):
    enqueue(conn, "reply")
    claim(conn)
    assert claim(conn) is None


def test_two_workers_never_take_the_same_job(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as setup:
        first, second = enqueue(setup, "a"), enqueue(setup, "b")
    a = psycopg.connect(migrated_db_url)
    b = psycopg.connect(migrated_db_url, autocommit=True)
    try:
        a.execute("SELECT 1")  # worker A's claim stays uncommitted: its row stays locked
        assert claim(a).id == first
        assert claim(b).id == second  # SKIP LOCKED: B doesn't wait for or take A's job
        assert claim(b) is None
        a.commit()
    finally:
        a.close()
        b.close()


def test_many_workers_at_once_take_every_job_exactly_once(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as setup:
        queued = {enqueue(setup, "n", {"i": i}) for i in range(60)}
    taken, lock = [], threading.Lock()

    def one_worker():
        with psycopg.connect(migrated_db_url, autocommit=True) as c:
            while (job := claim(c)) is not None:
                with lock:
                    taken.append(job.id)

    threads = [threading.Thread(target=one_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert sorted(taken) == sorted(queued)  # every job, none twice


# ---------- complete, fail, retry ----------


def test_complete(conn):
    job_id = enqueue(conn, "reply")
    job = claim(conn)
    assert complete(conn, job) is True
    assert row(conn, job_id)[:4] == ("done", 1, None, False)
    assert complete(conn, job) is False  # already done


@pytest.mark.parametrize(
    "attempts, seconds", [(1, 30), (2, 60), (3, 120), (5, 480), (8, 3600), (20, 3600)]
)
def test_backoff_doubles_and_is_capped(attempts, seconds):
    assert backoff(attempts) == datetime.timedelta(seconds=seconds)


def test_failure_retries_later_with_backoff(conn):
    job_id = enqueue(conn, "reply")
    assert fail(conn, claim(conn), "timeout") == "pending"
    status, attempts, error, locked, wait = row(conn, job_id)
    assert (status, attempts, error, locked) == ("pending", 1, "timeout", False)
    assert 25 < wait <= 30
    assert claim(conn) is None  # not before the backoff
    make_due(conn, job_id)
    assert fail(conn, claim(conn), "timeout again") == "pending"
    assert 55 < row(conn, job_id)[4] <= 60  # doubled


def test_attempts_used_up_means_dead(conn):
    job_id = enqueue(conn, "reply", max_attempts=2)
    assert fail(conn, claim(conn), "one") == "pending"
    make_due(conn, job_id)
    assert fail(conn, claim(conn), "two") == "dead"
    assert row(conn, job_id)[:3] == ("dead", 2, "two")
    make_due(conn, job_id)
    assert claim(conn) is None  # dead jobs are never picked


def test_fail_without_retry_is_dead_at_once(conn):
    job_id = enqueue(conn, "reply")
    assert fail(conn, claim(conn), "bad input", retry=False) == "dead"
    assert row(conn, job_id)[:2] == ("dead", 1)


def test_long_errors_are_cut(conn):
    job_id = enqueue(conn, "reply")
    fail(conn, claim(conn), "x" * 5000)
    assert len(row(conn, job_id)[2]) == jobs.MAX_ERROR_CHARS


# ---------- a worker that stopped mid-job ----------


def test_stale_lock_is_taken_over(conn):
    job_id = enqueue(conn, "reply")
    abandoned = claim(conn)
    go_stale(conn, job_id)
    again = claim(conn)
    assert (again.id, again.attempts) == (job_id, 2)
    # The first worker wakes up: it can no longer finish or fail the job.
    assert complete(conn, abandoned) is False
    assert fail(conn, abandoned, "late") is None
    assert complete(conn, again) is True


def test_a_recent_lock_is_respected(conn):
    job_id = enqueue(conn, "reply")
    claim(conn)
    conn.execute("UPDATE jobs SET locked_at = now() - interval '1 minute' WHERE id = %s", (job_id,))
    assert claim(conn) is None  # 1 minute < the 5-minute lock timeout
    assert claim(conn, lock_timeout=datetime.timedelta(seconds=30)).id == job_id


def test_worker_stopped_on_the_last_attempt_is_buried(conn):
    job_id = enqueue(conn, "reply", max_attempts=1)
    claim(conn)
    go_stale(conn, job_id)
    assert claim(conn) is None  # no attempts left to retry with
    buried = bury_abandoned(conn)
    assert [j.id for j in buried] == [job_id]
    assert row(conn, job_id)[:3] == ("dead", 1, "worker stopped during the last attempt")
    assert bury_abandoned(conn) == []


def test_bury_leaves_live_and_retryable_jobs_alone(conn):
    live = enqueue(conn, "a", max_attempts=1)
    claim(conn)  # running, fresh lock
    retryable = enqueue(conn, "b", max_attempts=3)
    claim(conn)
    go_stale(conn, retryable)  # stale but has attempts left: claim takes it over
    assert bury_abandoned(conn) == []
    assert row(conn, live)[0] == row(conn, retryable)[0] == "running"


# ---------- queue stats for /healthz ----------


def test_queue_stats(conn):
    assert queue_stats(conn) == {"depth": 0, "oldest_age_seconds": 0.0, "dead": 0}
    old, new = enqueue(conn, "a"), enqueue(conn, "b")
    enqueue(conn, "later", delay=datetime.timedelta(hours=1))  # not due: not counted
    conn.execute("UPDATE jobs SET run_at = now() - interval '100 seconds' WHERE id = %s", (old,))
    dead = enqueue(conn, "c")
    conn.execute("UPDATE jobs SET status = 'dead' WHERE id = %s", (dead,))
    stats = queue_stats(conn)
    assert stats["depth"] == 2 and stats["dead"] == 1
    assert 100 <= stats["oldest_age_seconds"] < 110
    assert new


def test_healthz_shows_the_queue(client, config):
    with psycopg.connect(config.database_url, autocommit=True) as c:
        enqueue(c, "reply")
    assert client.get("/healthz").json()["queue"]["depth"] == 1


# ---------- the worker ----------


class Alerts(list):
    def __call__(self, job, error):
        self.append((job.id, error))


def test_worker_runs_the_handler_and_completes(conn, caplog):
    seen = []
    w = Worker({"reply": lambda c, job: seen.append((c is conn, job.payload))}, alert=Alerts())
    job_id = enqueue(conn, "reply", {"x": 1})
    with caplog.at_level(logging.INFO, "app.worker"):
        assert w.run_once(conn) is True
    assert seen == [(True, {"x": 1})]
    assert row(conn, job_id)[0] == "done"
    assert f"job {job_id} (reply) done on attempt 1" in caplog.text


def test_worker_with_nothing_to_do(conn):
    assert Worker({}).run_once(conn) is False


def test_fails_twice_then_succeeds_with_retries_logged(conn, caplog):
    calls = []

    def flaky(c, job):
        calls.append(job.attempts)
        if job.attempts < 3:
            raise TimeoutError("provider slow")

    alerts = Alerts()
    w = Worker({"reply": flaky}, alert=alerts)
    job_id = enqueue(conn, "reply")
    with caplog.at_level(logging.INFO, "app.worker"):
        for _ in range(3):
            w.run_once(conn)
            make_due(conn, job_id)
    assert calls == [1, 2, 3]
    assert row(conn, job_id)[:3] == ("done", 3, None)
    assert "attempt 1/6 failed: TimeoutError: provider slow; retry in 30s" in caplog.text
    assert "attempt 2/6 failed: TimeoutError: provider slow; retry in 60s" in caplog.text
    assert alerts == []


def test_last_failure_alerts_once(conn):
    alerts = Alerts()

    def broken(c, job):
        raise ValueError("boom")

    w = Worker({"reply": broken}, alert=alerts)
    job_id = enqueue(conn, "reply", max_attempts=2)
    w.run_once(conn)
    make_due(conn, job_id)
    w.run_once(conn)
    assert alerts == [(job_id, "ValueError: boom")]
    assert row(conn, job_id)[:3] == ("dead", 2, "ValueError: boom")


def test_unknown_kind_is_dead_immediately(conn):
    alerts = Alerts()
    job_id = enqueue(conn, "mystery")
    assert Worker({}, alert=alerts).run_once(conn) is True
    assert row(conn, job_id)[:3] == ("dead", 1, "unknown job kind 'mystery'")
    assert alerts == [(job_id, "unknown job kind 'mystery'")]


def test_abandoned_last_attempt_alerts(conn):
    alerts = Alerts()
    job_id = enqueue(conn, "reply", max_attempts=1)
    claim(conn)
    go_stale(conn, job_id)
    assert Worker({}, alert=alerts).run_once(conn) is False
    assert alerts == [(job_id, "worker stopped during the last attempt")]


def test_duplicate_delivery_doesnt_double_side_effects(conn):
    conn.execute("CREATE TABLE sent (job_id bigint PRIMARY KEY)")  # the handler's own record

    def send_once(c, job):
        # The idempotent pattern: record the job id first; only a new record sends.
        if c.execute(
            "INSERT INTO sent (job_id) VALUES (%s) ON CONFLICT DO NOTHING RETURNING job_id",
            (job.id,),
        ).fetchone():
            c.execute("UPDATE counter SET n = n + 1")

    conn.execute("CREATE TABLE counter (n int)")
    conn.execute("INSERT INTO counter VALUES (0)")
    w = Worker({"send": send_once})
    job_id = enqueue(conn, "send")
    w.run_once(conn)
    # The worker died after sending but before marking done: the job is delivered again.
    conn.execute("UPDATE jobs SET status = 'running', attempts = 1 WHERE id = %s", (job_id,))
    go_stale(conn, job_id)
    w.run_once(conn)
    assert conn.execute("SELECT n FROM counter").fetchone()[0] == 1
    assert row(conn, job_id)[:2] == ("done", 2)


def test_job_taken_over_during_the_handler(conn, caplog):
    alerts = Alerts()

    def slow_then_fails(c, job):
        go_stale(c, job.id)  # meanwhile another worker may take the job over
        c.execute("UPDATE jobs SET locked_at = now() WHERE id = %s", (job.id,))
        raise RuntimeError("too late")

    def slow_then_succeeds(c, job):
        c.execute("UPDATE jobs SET locked_at = now() WHERE id = %s", (job.id,))

    for handler in (slow_then_fails, slow_then_succeeds):
        job_id = enqueue(conn, "reply")
        with caplog.at_level(logging.INFO, "app.worker"):
            Worker({"reply": handler}, alert=alerts).run_once(conn)
        assert row(conn, job_id)[0] == "running"  # the new owner decides
    assert alerts == []
    assert "done" not in caplog.text and "failed" not in caplog.text


def test_default_handlers_and_alert(conn, caplog):
    assert Worker().handlers is worker.HANDLERS
    job_id = enqueue(conn, "mystery")
    with caplog.at_level(logging.ERROR, "app.worker"):
        Worker().run_once(conn)
    assert f"job {job_id} (mystery) is dead after 1 attempts: unknown job kind" in caplog.text


# ---------- running and stopping ----------


def test_stop_during_a_job_finishes_it_first(migrated_db_url):
    pool = db.open_pool(migrated_db_url)
    try:
        w = Worker()
        done = []

        def long_job(c, job):
            w.stop()  # SIGTERM arrives while the job runs
            done.append(job.id)

        w.handlers = {"reply": long_job}
        with pool.connection() as c:
            first = enqueue(c, "reply")
            second = enqueue(c, "reply")
        w.run(pool, poll_seconds=0.01)
        with pool.connection() as c:
            assert row(c, first)[0] == "done"  # finished, not abandoned
            assert row(c, second)[0] == "pending"  # the next job waits for a new worker
        assert done == [first]
    finally:
        pool.close()


def test_idle_worker_polls_until_stopped(migrated_db_url):
    pool = db.open_pool(migrated_db_url)
    try:
        w = Worker({})
        timer = threading.Timer(0.3, w.stop)
        timer.start()
        w.run(pool, poll_seconds=0.05)  # returns once stopped
        assert w.stopping.is_set()
    finally:
        timer.cancel()
        pool.close()


def test_main_migrates_runs_and_restores_signal_handlers(env_vars, caplog):
    before = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    w = Worker({})
    w.stop()  # stop at once: the loop exits straight away
    with caplog.at_level(logging.INFO, "app.worker"):
        main(worker=w, config=load_config(env_vars))
    assert {sig: signal.getsignal(sig) for sig in before} == before
    assert "worker started" in caplog.text and "worker stopped" in caplog.text
    with psycopg.connect(env_vars["DATABASE_URL"]) as c:  # migrations ran
        assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_main_uses_defaults(monkeypatch, env_vars):
    ran = []
    monkeypatch.setattr(worker, "load_config", lambda: load_config(env_vars))
    monkeypatch.setattr(Worker, "run", lambda self, pool: ran.append(self))
    main()
    assert len(ran) == 1 and ran[0].handlers is worker.HANDLERS


def test_unknown_kind_taken_over_meanwhile_doesnt_alert_twice(conn, monkeypatch):
    alerts = Alerts()
    enqueue(conn, "mystery")
    monkeypatch.setattr(jobs, "fail", lambda *args, **kwargs: None)  # another worker owns it now
    assert Worker({}, alert=alerts).run_once(conn) is True
    assert alerts == []


def test_busy_worker_drains_a_backlog_without_pausing(migrated_db_url):
    pool = db.open_pool(migrated_db_url)
    try:
        done = []
        w = Worker()

        def quick(c, job):
            done.append(job.id)
            if len(done) == 5:
                w.stop()

        w.handlers = {"reply": quick}
        with pool.connection() as c:
            for _ in range(5):
                enqueue(c, "reply")
        started = time.monotonic()
        w.run(pool, poll_seconds=5)  # a pause between jobs would take 5 s each
        assert len(done) == 5
        assert time.monotonic() - started < 4
    finally:
        pool.close()
