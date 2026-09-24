"""Lead scoring (PRD §5.3): hot / warm / cold plus review flags, computed by code from the
pack's rules, never by the AI. The rules live in the pack (D-012); this module only knows
the generic operators the pack loader already validated.
"""

import calendar
import datetime
import re
from dataclasses import dataclass

from app.packs import Condition, Pack

YEAR_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class Score:
    level: str  # "hot", "warm" or "cold"
    flags: tuple[str, ...]  # shown to the counsellor; they don't change the level


def _present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, list | tuple):
        return len(value) > 0
    return True


def _key(value):
    """Comparable, hashable form: text ignores case and extra spaces; numbers and booleans
    compare strictly (True never equals 1); anything else (a list or dict where one value
    belongs) matches nothing."""
    if isinstance(value, str):
        return ("str", " ".join(value.split()).casefold())
    if isinstance(value, int | float):
        return (type(value).__name__, value)
    return ("unmatchable", id(value))


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _add_months(day: datetime.date, months: int) -> datetime.date:
    """Same day `months` later; the 31st becomes the month's last day when needed."""
    total = day.year * 12 + day.month - 1 + months
    year, month = divmod(total, 12)
    month += 1
    return datetime.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _within_months(value, months: int, today: datetime.date) -> bool:
    """Intake month hasn't passed, and its first day is at most `months` from today."""
    match = YEAR_MONTH.match(value) if isinstance(value, str) else None
    if not match:
        return False
    year, month = int(match[1]), int(match[2])
    if (year, month) < (today.year, today.month):
        return False  # already passed; this month still counts as upcoming
    return datetime.date(year, month, 1) <= _add_months(today, months)


def _holds(cond: Condition, profile: dict, settings: dict, today: datetime.date) -> bool:
    if cond.any:
        return any(_holds(c, profile, settings, today) for c in cond.any)
    value = profile.get(cond.field)
    op = cond.op
    if op == "present":
        return _present(value)
    if op == "absent":
        return not _present(value)
    if op in ("eq", "ne"):
        # The loader guarantees non-blank comparison values, so a missing value never matches.
        same = _key(value) == _key(cond.value)
        return same if op == "eq" else not same  # unknown is "not equal"
    if op in ("in", "not_in"):
        inside = _key(value) in {_key(v) for v in cond.values}
        return inside if op == "in" else not inside
    if op in ("gte", "lte"):
        if not _is_int(value):
            return False
        return value >= cond.value if op == "gte" else value <= cond.value
    if op == "within_months":
        return _within_months(value, cond.months, today)
    # overlaps_setting (the loader allows no other op)
    wanted = settings.get(cond.setting)
    if not isinstance(value, list | tuple) or not isinstance(wanted, list | tuple):
        return False
    return bool({_key(v) for v in value} & {_key(v) for v in wanted})


def score(pack: Pack, profile: dict, settings: dict, today: datetime.date) -> Score:
    """Score one contact.

    profile: the contact's pack fields plus the built-ins (phone, name, adult).
    settings: the tenant's pack settings (e.g. served_countries).
    today: the date in the tenant's timezone, passed in so results never depend on the clock.
    Bad or missing values never raise; they just don't satisfy a rule.
    """
    if not isinstance(today, datetime.date) or isinstance(today, datetime.datetime):
        raise TypeError("today must be a datetime.date")
    profile = profile if isinstance(profile, dict) else {}
    settings = settings if isinstance(settings, dict) else {}

    def all_hold(conditions) -> bool:
        return all(_holds(c, profile, settings, today) for c in conditions)

    rules = pack.scoring
    level = "hot" if all_hold(rules.hot) else "warm" if all_hold(rules.warm) else "cold"
    flags = tuple(flag.name for flag in rules.flags if all_hold(flag.when))
    return Score(level, flags)
