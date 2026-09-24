"""Appointment slots and bookings (P2.4, PRD F14-F15, D-020)."""

import datetime
import threading
import zoneinfo

import psycopg
import pytest

from app.booking import BookingError, Slot, book, cancel, list_slots

UTC = datetime.UTC
DHAKA = zoneinfo.ZoneInfo("Asia/Dhaka")
LONDON = zoneinfo.ZoneInfo("Europe/London")
MONDAY = datetime.date(2026, 10, 5)
SUNDAY_BEFORE = datetime.datetime(2026, 10, 4, 12, 0, tzinfo=DHAKA)


def at(day, hour, minute=0, tz=DHAKA):
    return datetime.datetime.combine(day, datetime.time(hour, minute), tz)


# ---------- helpers ----------


@pytest.fixture
def conn(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as c:
        yield c


def one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def tenant(conn, slug="acme", tz="Asia/Dhaka"):
    return one(
        conn,
        "INSERT INTO tenants (slug, name, fallback_text, timezone) VALUES (%s, 'A', 'x', %s)"
        " RETURNING id",
        (slug, tz),
    )


def branch(conn, t, name="Banani"):
    return one(
        conn, "INSERT INTO branches (tenant_id, name) VALUES (%s, %s) RETURNING id", (t, name)
    )


def schedule(conn, t, b, weekday, start, end, minutes=60, capacity=1):
    conn.execute(
        "INSERT INTO schedules (tenant_id, branch_id, weekday, start_time, end_time,"
        " slot_minutes, capacity) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (t, b, weekday, start, end, minutes, capacity),
    )


def contact(conn, t, ext="user-1"):
    found = conn.execute(
        "SELECT id FROM channels WHERE tenant_id = %s AND type = 'web'", (t,)
    ).fetchone()  # one web channel per company
    ch = (
        found[0]
        if found
        else one(
            conn, "INSERT INTO channels (tenant_id, type) VALUES (%s, 'web') RETURNING id", (t,)
        )
    )
    return one(
        conn,
        "INSERT INTO contacts (tenant_id, channel_id, external_user_id) VALUES (%s, %s, %s)"
        " RETURNING id",
        (t, ch, ext),
    )


@pytest.fixture
def shop(conn):
    """A Dhaka company with one branch open Mondays 10:00-12:00, 1-hour slots, 2 seats."""
    t = tenant(conn)
    b = branch(conn, t)
    schedule(conn, t, b, 1, "10:00", "12:00", 60, 2)
    return t, b


def starts(slots):
    return [(s.start.astimezone(UTC).strftime("%Y-%m-%d %H:%M"), s.remaining) for s in slots]


def local_starts(slots, tz=DHAKA):
    return [s.start.astimezone(tz).strftime("%a %H:%M") for s in slots]


# ---------- slots from the weekly schedule ----------


def test_weekly_schedule_becomes_slots(conn, shop):
    t, b = shop
    slots = list_slots(conn, t, now=SUNDAY_BEFORE, limit=10, days=7)
    assert slots == [
        Slot(b, at(MONDAY, 10), at(MONDAY, 11), 2),
        Slot(b, at(MONDAY, 11), at(MONDAY, 12), 2),
    ]


def test_slots_repeat_every_week(conn, shop):
    t, _ = shop
    slots = list_slots(conn, t, now=SUNDAY_BEFORE, limit=10, days=14)
    assert local_starts(slots) == ["Mon 10:00", "Mon 11:00", "Mon 10:00", "Mon 11:00"]
    assert slots[2].start - slots[0].start == datetime.timedelta(days=7)


@pytest.mark.parametrize(
    "end, expected",
    [
        ("11:30", ["Mon 10:00", "Mon 10:30", "Mon 11:00"]),  # 11:00-11:30 ends exactly at closing
        ("11:45", ["Mon 10:00", "Mon 10:30", "Mon 11:00"]),  # 11:30-12:00 would cross it
    ],
)
def test_closing_time_boundary(conn, end, expected):
    t = tenant(conn)
    schedule(conn, t, branch(conn, t), 1, "10:00", end, 30, 1)
    assert local_starts(list_slots(conn, t, now=SUNDAY_BEFORE, limit=10, days=7)) == expected


def test_holidays_are_closed(conn, shop):
    t, _ = shop
    conn.execute("INSERT INTO holidays (tenant_id, date) VALUES (%s, %s)", (t, MONDAY))
    slots = list_slots(conn, t, now=SUNDAY_BEFORE, limit=10, days=14)
    assert {s.start.date() for s in slots} == {MONDAY + datetime.timedelta(days=7)}


@pytest.mark.parametrize(
    "now, expected",
    [
        (at(MONDAY, 9, 59), ["Mon 10:00", "Mon 11:00"]),
        (at(MONDAY, 10, 0), ["Mon 11:00"]),  # starting right now is too late
        (at(MONDAY, 10, 30), ["Mon 11:00"]),
        (at(MONDAY, 11, 0), []),
    ],
)
def test_past_slots_are_gone(conn, shop, now, expected):
    t, _ = shop
    assert local_starts(list_slots(conn, t, now=now, limit=10, days=1)) == expected


def test_now_in_another_timezone_means_the_same_instant(conn, shop):
    t, _ = shop
    now = at(MONDAY, 10, 30).astimezone(UTC)  # 04:30 UTC
    assert local_starts(list_slots(conn, t, now=now, limit=10, days=1)) == ["Mon 11:00"]


def test_friday_closed_when_no_friday_schedule(conn):
    t = tenant(conn)
    b = branch(conn, t)
    for weekday in (1, 2, 3, 4, 6, 7):  # every day but Friday (5)
        schedule(conn, t, b, weekday, "10:00", "11:00")
    slots = list_slots(conn, t, now=SUNDAY_BEFORE, limit=20, days=8)  # Sunday's slot passed
    days = [s.start.strftime("%a") for s in slots]
    assert "Fri" not in days
    assert len(days) == 6


def test_empty_schedule_means_no_slots_not_an_error(conn):
    t = tenant(conn)
    branch(conn, t)
    assert list_slots(conn, t, now=SUNDAY_BEFORE) == []


def test_asks_for_five_gets_the_two_that_exist(conn, shop):
    t, _ = shop
    assert len(list_slots(conn, t, now=SUNDAY_BEFORE, limit=5, days=7)) == 2


def test_limit_takes_the_soonest(conn, shop):
    t, _ = shop
    assert local_starts(list_slots(conn, t, now=SUNDAY_BEFORE, limit=1)) == ["Mon 10:00"]


def test_days_window(conn, shop):
    t, _ = shop
    assert list_slots(conn, t, now=SUNDAY_BEFORE, days=1) == []  # only Sunday
    assert len(list_slots(conn, t, now=SUNDAY_BEFORE, days=2)) == 2


def test_from_date_starts_later(conn, shop):
    t, _ = shop
    later = MONDAY + datetime.timedelta(days=7)
    slots = list_slots(conn, t, now=SUNDAY_BEFORE, from_date=later, limit=10, days=7)
    assert {s.start.date() for s in slots} == {later}


@pytest.mark.parametrize(
    "from_date",
    [datetime.date(2020, 1, 1), None, "2026-10-12", datetime.datetime(2026, 10, 12, 9, 0)],
)
def test_from_date_in_the_past_or_junk_means_today(conn, shop, from_date):
    t, _ = shop
    slots = list_slots(conn, t, now=SUNDAY_BEFORE, from_date=from_date, limit=10, days=7)
    assert len(slots) == 2


def test_overlapping_schedule_rows_dont_duplicate_slots(conn):
    t = tenant(conn)
    b = branch(conn, t)
    schedule(conn, t, b, 1, "10:00", "12:00", 60, 1)
    schedule(conn, t, b, 1, "11:00", "13:00", 60, 3)
    slots = list_slots(conn, t, now=SUNDAY_BEFORE, limit=10, days=7)
    assert [(local_starts([s])[0], s.remaining) for s in slots] == [
        ("Mon 10:00", 1),
        ("Mon 11:00", 3),  # both rows give 11:00: one slot, the larger capacity
        ("Mon 12:00", 3),
    ]


def test_branches_are_separate_and_can_be_filtered(conn, shop):
    t, b = shop
    online = branch(conn, t, "Online")
    schedule(conn, t, online, 1, "10:00", "11:00", 60, 5)
    both = list_slots(conn, t, now=SUNDAY_BEFORE, limit=10, days=7)
    assert [(s.branch_id, s.remaining) for s in both] == [(b, 2), (online, 5), (b, 2)]
    only = list_slots(conn, t, now=SUNDAY_BEFORE, branch_id=online, limit=10, days=7)
    assert [s.branch_id for s in only] == [online]


def test_another_companys_schedule_never_shows(conn, shop):
    t, _ = shop
    other = tenant(conn, "other")
    schedule(conn, other, branch(conn, other), 1, "15:00", "16:00")
    assert local_starts(list_slots(conn, t, now=SUNDAY_BEFORE, limit=10, days=7)) == [
        "Mon 10:00",
        "Mon 11:00",
    ]


# ---------- timezones ----------


def test_dhaka_has_no_daylight_saving(conn, shop):
    t, _ = shop
    slots = list_slots(conn, t, now=SUNDAY_BEFORE, limit=1)
    assert starts(slots) == [("2026-10-05 04:00", 2)]  # 10:00 Dhaka = 04:00 UTC all year


def test_london_on_the_day_clocks_go_back(conn):
    t = tenant(conn, tz="Europe/London")
    b = branch(conn, t)
    schedule(conn, t, b, 6, "10:00", "11:00")  # Saturday, still summer time
    schedule(conn, t, b, 7, "10:00", "11:00")  # Sunday 25 Oct 2026: back to GMT at 02:00
    now = datetime.datetime(2026, 10, 23, 12, 0, tzinfo=LONDON)
    assert starts(list_slots(conn, t, now=now, limit=2)) == [
        ("2026-10-24 09:00", 1),  # 10:00 BST
        ("2026-10-25 10:00", 1),  # 10:00 GMT
    ]


def test_london_repeated_hour_uses_the_first(conn):
    t = tenant(conn, tz="Europe/London")
    schedule(conn, t, branch(conn, t), 7, "01:30", "02:30")
    now = datetime.datetime(2026, 10, 24, 12, 0, tzinfo=LONDON)
    slot = list_slots(conn, t, now=now, limit=1)[0]
    assert slot.start.astimezone(UTC) == datetime.datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    real = slot.end.astimezone(UTC) - slot.start.astimezone(UTC)
    assert real == datetime.timedelta(hours=1)  # a real hour, though the wall clock says 0


def test_booking_the_second_repeated_hour_is_refused(conn):
    t = tenant(conn, tz="Europe/London")
    b = branch(conn, t)
    schedule(conn, t, b, 7, "01:30", "02:30")
    now = datetime.datetime(2026, 10, 24, 12, 0, tzinfo=LONDON)
    second = datetime.datetime(2026, 10, 25, 1, 30, fold=1, tzinfo=LONDON)  # 01:30 GMT
    c = contact(conn, t)
    with pytest.raises(BookingError, match="that time isn't an open slot"):
        book(conn, t, c, b, second, now=now)
    first = second.replace(fold=0)  # 01:30 BST, the real slot
    assert book(conn, t, c, b, first, now=now)


def test_london_skipped_hour_has_no_slot(conn):
    t = tenant(conn, tz="Europe/London")
    schedule(conn, t, branch(conn, t), 7, "00:30", "03:30")  # 29 Mar 2026: 01:00 → 02:00
    now = datetime.datetime(2026, 3, 28, 12, 0, tzinfo=LONDON)
    slots = list_slots(conn, t, now=now, limit=10, days=1 + 1)
    assert local_starts(slots, LONDON) == ["Sun 00:30", "Sun 02:30"]  # 01:30 doesn't exist


def test_an_hour_that_doesnt_exist_gives_no_slot(conn):
    t = tenant(conn, tz="Europe/London")
    schedule(conn, t, branch(conn, t), 7, "01:00", "02:00")  # 29 Mar 2026 skips 01:00-02:00
    now = datetime.datetime(2026, 3, 28, 12, 0, tzinfo=LONDON)
    assert list_slots(conn, t, now=now, limit=10, days=2) == []


def test_invalid_company_timezone_is_a_clear_error(conn):
    t = tenant(conn, tz="Mars/Olympus")
    with pytest.raises(BookingError, match="company timezone 'Mars/Olympus' is not valid"):
        list_slots(conn, t, now=SUNDAY_BEFORE)


def test_unknown_company(conn):
    with pytest.raises(BookingError, match="company not found"):
        list_slots(conn, 999_999, now=SUNDAY_BEFORE)


@pytest.mark.parametrize("now", [datetime.datetime(2026, 10, 4, 12, 0), "2026-10-04", None])
def test_now_must_be_timezone_aware(conn, shop, now):
    with pytest.raises(TypeError):
        list_slots(conn, shop[0], now=now)


# ---------- booking ----------


def test_book_takes_a_seat(conn, shop):
    t, b = shop
    c = contact(conn, t)
    booking = book(conn, t, c, b, at(MONDAY, 10), now=SUNDAY_BEFORE)
    assert one(conn, "SELECT status FROM bookings WHERE id = %s", (booking,)) == "booked"
    assert list_slots(conn, t, now=SUNDAY_BEFORE, limit=1)[0].remaining == 1


def test_full_slot_disappears_and_refuses_more(conn, shop):
    t, b = shop
    for ext in ("u1", "u2"):
        book(conn, t, contact(conn, t, ext), b, at(MONDAY, 10), now=SUNDAY_BEFORE)
    assert local_starts(list_slots(conn, t, now=SUNDAY_BEFORE, limit=1)) == ["Mon 11:00"]
    with pytest.raises(BookingError, match="that slot is full"):
        book(conn, t, contact(conn, t, "u3"), b, at(MONDAY, 10), now=SUNDAY_BEFORE)


def test_retrying_the_same_booking_returns_the_same_id(conn, shop):
    t, b = shop
    c = contact(conn, t)
    first = book(conn, t, c, b, at(MONDAY, 10), now=SUNDAY_BEFORE)
    again = book(conn, t, c, b, at(MONDAY, 10).astimezone(UTC), now=SUNDAY_BEFORE)
    assert again == first
    assert one(conn, "SELECT count(*) FROM bookings") == 1


@pytest.mark.parametrize(
    "when",
    [
        at(MONDAY, 10, 15),  # not on the schedule's grid
        at(MONDAY, 12),  # after closing
        at(MONDAY + datetime.timedelta(days=1), 10),  # Tuesday: closed
        at(MONDAY - datetime.timedelta(days=7), 10),  # last week: past
    ],
)
def test_book_refuses_times_that_arent_open_slots(conn, shop, when):
    t, b = shop
    with pytest.raises(BookingError, match="that time isn't an open slot"):
        book(conn, t, contact(conn, t), b, when, now=SUNDAY_BEFORE)


def test_book_refuses_a_holiday(conn, shop):
    t, b = shop
    conn.execute("INSERT INTO holidays (tenant_id, date) VALUES (%s, %s)", (t, MONDAY))
    with pytest.raises(BookingError, match="that time isn't an open slot"):
        book(conn, t, contact(conn, t), b, at(MONDAY, 10), now=SUNDAY_BEFORE)


def test_book_refuses_another_companys_branch(conn, shop):
    t, _ = shop
    other = tenant(conn, "other")
    other_branch = branch(conn, other)
    schedule(conn, other, other_branch, 1, "10:00", "12:00")
    with pytest.raises(BookingError, match="branch not found"):
        book(conn, t, contact(conn, t), other_branch, at(MONDAY, 10), now=SUNDAY_BEFORE)


def test_book_refuses_another_companys_contact(conn, shop):
    t, b = shop
    stranger = contact(conn, tenant(conn, "other"))
    with pytest.raises(BookingError, match="contact not found"):
        book(conn, t, stranger, b, at(MONDAY, 10), now=SUNDAY_BEFORE)
    assert one(conn, "SELECT count(*) FROM bookings") == 0


@pytest.mark.parametrize("field", ["now", "slot_start"])
def test_book_needs_timezone_aware_times(conn, shop, field):
    t, b = shop
    args = {"now": SUNDAY_BEFORE, "slot_start": at(MONDAY, 10)}
    args[field] = args[field].replace(tzinfo=None)
    with pytest.raises(TypeError):
        book(conn, t, contact(conn, t), b, args["slot_start"], now=args["now"])


def test_two_people_racing_for_the_last_seat(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as setup:
        t = tenant(setup)
        b = branch(setup, t)
        schedule(setup, t, b, 1, "10:00", "11:00", 60, 1)  # one seat
        first_contact, second_contact = contact(setup, t, "u1"), contact(setup, t, "u2")
    first = psycopg.connect(migrated_db_url)
    second = psycopg.connect(migrated_db_url, autocommit=True)
    outcome = {}
    try:
        first.execute("SELECT 1")  # open transaction: the booking commits only with it
        book(first, t, first_contact, b, at(MONDAY, 10), now=SUNDAY_BEFORE)

        def other_person():
            try:
                book(second, t, second_contact, b, at(MONDAY, 10), now=SUNDAY_BEFORE)
                outcome["second"] = "booked"
            except BookingError as error:
                outcome["second"] = str(error)

        worker = threading.Thread(target=other_person)
        worker.start()
        worker.join(timeout=1)
        assert worker.is_alive()  # waits for the first booking to finish
        first.commit()
        worker.join(timeout=10)
        assert outcome == {"second": "that slot is full"}
        assert second.execute("SELECT count(*) FROM bookings").fetchone()[0] == 1
    finally:
        first.close()
        second.close()


# ---------- cancel ----------


def test_cancel_frees_the_seat(conn, shop):
    t, b = shop
    c = contact(conn, t)
    booking = book(conn, t, c, b, at(MONDAY, 10), now=SUNDAY_BEFORE)
    cancel(conn, t, booking)
    assert list_slots(conn, t, now=SUNDAY_BEFORE, limit=1)[0].remaining == 2
    assert book(conn, t, c, b, at(MONDAY, 10), now=SUNDAY_BEFORE) != booking  # a new booking


def test_cancel_twice_is_refused(conn, shop):
    t, b = shop
    booking = book(conn, t, contact(conn, t), b, at(MONDAY, 10), now=SUNDAY_BEFORE)
    cancel(conn, t, booking)
    with pytest.raises(BookingError, match="no active booking"):
        cancel(conn, t, booking)


def test_cancel_another_companys_booking_is_refused(conn, shop):
    t, b = shop
    booking = book(conn, t, contact(conn, t), b, at(MONDAY, 10), now=SUNDAY_BEFORE)
    with pytest.raises(BookingError, match="no active booking"):
        cancel(conn, tenant(conn, "other"), booking)
    assert one(conn, "SELECT status FROM bookings WHERE id = %s", (booking,)) == "booked"
