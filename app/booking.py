"""Appointment slots and bookings (PRD F14-F15, D-020): a counselling session, a vet visit,
a check-up; the pack names it, this module doesn't care.

Slots come from each branch's weekly schedule, in the company's own timezone, minus holidays,
past times and full slots. Booking locks the branch row, so two people racing for the last
seat are handled one after the other and exactly one gets it.
"""

import datetime
import zoneinfo
from dataclasses import dataclass

from psycopg import errors

UTC = datetime.UTC
DEFAULT_DAYS = 14  # how far ahead list_slots looks


class BookingError(ValueError):
    """The booking or cancellation was refused; the message says why."""


@dataclass(frozen=True)
class Slot:
    branch_id: int
    start: datetime.datetime  # timezone-aware, in the company's timezone; compare in UTC,
    end: datetime.datetime  # since Python ignores `fold` within one zone (repeated hour)
    remaining: int  # seats left


def _aware(value, name) -> None:
    if not isinstance(value, datetime.datetime) or value.utcoffset() is None:
        raise TypeError(f"{name} must be a timezone-aware datetime")


def _timezone(conn, tenant_id) -> zoneinfo.ZoneInfo:
    row = conn.execute("SELECT timezone FROM tenants WHERE id = %s", (tenant_id,)).fetchone()
    if row is None:
        raise BookingError("company not found")
    try:
        return zoneinfo.ZoneInfo(row[0])
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        raise BookingError(f"company timezone {row[0]!r} is not valid") from None


def _local(day: datetime.date, minutes: int, tz) -> datetime.datetime | None:
    """`minutes` after local midnight on `day`, or None if that wall time doesn't exist
    (skipped when clocks go forward). A repeated wall time (clocks go back) is the first."""
    naive = datetime.datetime.combine(day, datetime.time(minutes // 60, minutes % 60))
    aware = naive.replace(tzinfo=tz)
    if aware.astimezone(UTC).astimezone(tz).replace(tzinfo=None) != naive:
        return None
    return aware


def _minutes(t: datetime.time) -> int:
    return t.hour * 60 + t.minute


SCHEDULES = """
SELECT branch_id, weekday, start_time, end_time, slot_minutes, capacity FROM schedules
WHERE tenant_id = %s AND (%s::bigint IS NULL OR branch_id = %s)
"""
HOLIDAYS = "SELECT date FROM holidays WHERE tenant_id = %s AND date BETWEEN %s AND %s"
BOOKED = """
SELECT branch_id, slot_start, count(*) FROM bookings
WHERE tenant_id = %s AND status = 'booked' AND slot_start >= %s AND slot_start < %s
GROUP BY branch_id, slot_start
"""


def _slots(conn, tenant_id, tz, first, last, branch_id, now) -> list[Slot]:
    """Every future slot from local date `first` to `last` (inclusive), full ones included."""
    rows = conn.execute(SCHEDULES, (tenant_id, branch_id, branch_id)).fetchall()
    holidays = {d for (d,) in conn.execute(HOLIDAYS, (tenant_id, first, last))}
    capacity: dict[tuple, int] = {}  # (branch, start) → seats; overlapping rows: the larger
    ends: dict[tuple, datetime.datetime] = {}
    day = first
    while day <= last:
        if day not in holidays:
            for branch, weekday, start, end, length, seats in rows:
                if weekday != day.isoweekday():
                    continue
                m = _minutes(start)
                while m + length <= _minutes(end):  # a slot ending exactly at closing counts
                    begins = _local(day, m, tz)
                    if begins is not None and begins.astimezone(UTC) > now.astimezone(UTC):
                        key = (branch, begins.astimezone(UTC))  # UTC: a repeated hour differs
                        capacity[key] = max(capacity.get(key, 0), seats)
                        ends[key] = key[1] + datetime.timedelta(minutes=length)
                    m += length
        day += datetime.timedelta(days=1)
    if not capacity:
        return []
    window_start = datetime.datetime.combine(first, datetime.time(), tz)
    window_end = datetime.datetime.combine(last + datetime.timedelta(days=1), datetime.time(), tz)
    taken = {
        (branch, start.astimezone(UTC)): count
        for branch, start, count in conn.execute(BOOKED, (tenant_id, window_start, window_end))
    }
    slots = [
        Slot(
            branch,
            start.astimezone(tz),
            ends[(branch, start)].astimezone(tz),
            seats - taken.get((branch, start), 0),
        )
        for (branch, start), seats in capacity.items()
    ]
    return sorted(slots, key=lambda s: (s.start.astimezone(UTC), s.branch_id))


def list_slots(
    conn, tenant_id, *, now, branch_id=None, from_date=None, limit=5, days=DEFAULT_DAYS
) -> list[Slot]:
    """The next `limit` open slots (seats left), soonest first, within `days` of the start
    date (the later of today and `from_date`, in the company's timezone). Empty list when
    nothing is open: not an error."""
    _aware(now, "now")
    tz = _timezone(conn, tenant_id)
    today = now.astimezone(tz).date()
    plain_date = isinstance(from_date, datetime.date) and not isinstance(
        from_date, datetime.datetime
    )
    first = max(today, from_date) if plain_date else today
    last = first + datetime.timedelta(days=days - 1)
    open_slots = [
        s for s in _slots(conn, tenant_id, tz, first, last, branch_id, now) if s.remaining > 0
    ]
    return open_slots[:limit]


def book(conn, tenant_id, contact_id, branch_id, slot_start, *, now) -> int:
    """Book one seat. Returns the booking id; booking the same slot again for the same
    contact returns the same id (safe to retry). Raises BookingError when the time isn't
    an open slot (past, holiday, not on the schedule) or it's full."""
    _aware(now, "now")
    _aware(slot_start, "slot_start")
    with conn.transaction():
        locked = conn.execute(
            "SELECT id FROM branches WHERE tenant_id = %s AND id = %s FOR UPDATE",
            (tenant_id, branch_id),
        ).fetchone()  # one booking per branch at a time: no double-booking the last seat
        if locked is None:
            raise BookingError("branch not found")
        existing = conn.execute(
            "SELECT id FROM bookings WHERE tenant_id = %s AND contact_id = %s"
            " AND branch_id = %s AND slot_start = %s AND status = 'booked'",
            (tenant_id, contact_id, branch_id, slot_start),
        ).fetchone()
        if existing is not None:
            return existing[0]
        tz = _timezone(conn, tenant_id)
        day = slot_start.astimezone(tz).date()
        slot = next(
            (
                s
                for s in _slots(conn, tenant_id, tz, day, day, branch_id, now)
                if s.start.astimezone(UTC) == slot_start.astimezone(UTC)
            ),
            None,
        )
        if slot is None:
            raise BookingError("that time isn't an open slot")
        if slot.remaining <= 0:
            raise BookingError("that slot is full")
        try:
            return conn.execute(
                "INSERT INTO bookings (tenant_id, contact_id, branch_id, slot_start)"
                " VALUES (%s, %s, %s, %s) RETURNING id",
                (tenant_id, contact_id, branch_id, slot_start),
            ).fetchone()[0]
        except errors.ForeignKeyViolation:
            raise BookingError("contact not found") from None


def cancel(conn, tenant_id, booking_id) -> None:
    """Cancel an active booking; its seat is free again at once."""
    cancelled = conn.execute(
        "UPDATE bookings SET status = 'cancelled'"
        " WHERE tenant_id = %s AND id = %s AND status = 'booked' RETURNING id",
        (tenant_id, booking_id),
    ).fetchone()
    if cancelled is None:
        raise BookingError("no active booking with that id")
