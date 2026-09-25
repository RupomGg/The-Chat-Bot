"""The worker process (PRD §8): claims jobs and runs their handler, one at a time.

Run with:  python -m app.worker
Stops gracefully on SIGTERM/SIGINT: the current job finishes first. Handlers must be
idempotent (a job can be delivered twice if a worker dies after the work but before
marking it done); use the job id as the idempotency key.
"""

import logging
import signal
import threading

from app import db, jobs
from app.config import load_config

log = logging.getLogger("app.worker")

HANDLERS: dict = {}  # kind → handler(conn, job); later portions register theirs
POLL_SECONDS = 1.0


def _alert(job: jobs.Job, error: str) -> None:
    """Default alert: an error log line (Sentry and the operator bot hook in later)."""
    log.error("job %s (%s) is dead after %s attempts: %s", job.id, job.kind, job.attempts, error)


class Worker:
    def __init__(self, handlers=None, *, alert=_alert, lock_timeout=jobs.LOCK_TIMEOUT):
        self.handlers = HANDLERS if handlers is None else handlers
        self.alert = alert
        self.lock_timeout = lock_timeout
        self.stopping = threading.Event()

    def run_once(self, conn) -> bool:
        """Process at most one job. False when nothing was due."""
        for job in jobs.bury_abandoned(conn, lock_timeout=self.lock_timeout):
            self.alert(job, "worker stopped during the last attempt")
        job = jobs.claim(conn, lock_timeout=self.lock_timeout)
        if job is None:
            return False
        handler = self.handlers.get(job.kind)
        if handler is None:
            error = f"unknown job kind {job.kind!r}"
            if jobs.fail(conn, job, error, retry=False) == "dead":
                self.alert(job, error)
            return True
        try:
            handler(conn, job)
        except Exception as exc:  # any handler failure is recorded, never lost
            error = f"{type(exc).__name__}: {exc}"
            status = jobs.fail(conn, job, error)
            if status == "dead":
                self.alert(job, error)
            elif status == "pending":
                log.warning(
                    "job %s (%s) attempt %s/%s failed: %s; retry in %ss",
                    job.id,
                    job.kind,
                    job.attempts,
                    job.max_attempts,
                    error,
                    int(jobs.backoff(job.attempts).total_seconds()),
                )
            return True
        if jobs.complete(conn, job):
            log.info("job %s (%s) done on attempt %s", job.id, job.kind, job.attempts)
        return True

    def run(self, pool, *, poll_seconds=POLL_SECONDS) -> None:
        """Loop until stop() is called; the job in progress always finishes first."""
        while not self.stopping.is_set():
            with pool.connection() as conn:
                busy = self.run_once(conn)
            if not busy:
                self.stopping.wait(poll_seconds)

    def stop(self, *_signal_args) -> None:
        self.stopping.set()


def main(worker=None, config=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = config or load_config()
    worker = worker or Worker()
    db.wait_for_db(config.database_url)
    db.migrate(config.database_url)  # safe if the web service migrates at the same time
    previous = {sig: signal.signal(sig, worker.stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    pool = db.open_pool(config.database_url)
    try:
        log.info("worker started")
        worker.run(pool)
    finally:
        pool.close()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        log.info("worker stopped")


if __name__ == "__main__":
    main()
