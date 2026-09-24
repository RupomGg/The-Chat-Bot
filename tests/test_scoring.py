"""Lead scoring (P2.3, PRD §5.3): study_abroad rules from pack.toml, plus every generic operator."""

import dataclasses
import datetime
import pathlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.packs import Condition, Flag, Scoring, load_pack
from app.scoring import Score, _add_months, score

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "packs"
STUDY = load_pack("study_abroad")
PETS = load_pack("pet_care_sample", FIXTURES)
TODAY = datetime.date(2026, 1, 15)
SERVED = {"served_countries": ["UK", "Malaysia"]}


def hot_student(**changes):
    """A profile that meets every Hot rule on TODAY; tests change one thing at a time."""
    profile = {
        "phone": "+8801712345678",
        "intake": "2026-09",
        "english_test": "ielts",
        "english_score": "6.5",
        "funding": "self_family",
        "target_countries": ["uk"],
    }
    profile.update(changes)
    return {k: v for k, v in profile.items() if v is not ...}  # ... = remove the key


def level(profile, settings=SERVED, today=TODAY):
    return score(STUDY, profile, settings, today).level


# ---------- study_abroad: Hot ----------


def test_hot_when_every_rule_holds():
    assert score(STUDY, hot_student(), SERVED, TODAY) == Score("hot", ())


@pytest.mark.parametrize(
    "changes",
    [
        {"phone": ...},
        {"phone": ""},
        {"intake": ...},
        {"intake": "2027-12"},  # too far for Hot (23 months), and too far for Warm
        {"english_score": ..., "english_test": "none"},
        {"english_score": ..., "english_test": ...},
        {"funding": "scholarship_only"},
        {"target_countries": ["canada"]},
        {"target_countries": []},
    ],
)
def test_each_hot_rule_on_its_own(changes):
    assert level(hot_student(**changes)) != "hot"


@pytest.mark.parametrize("test", ["moi", "booked", "MOI"])
def test_moi_or_a_booked_test_counts_as_english(test):
    assert level(hot_student(english_score=..., english_test=test)) == "hot"


def test_unknown_funding_doesnt_block_hot():
    assert level(hot_student(funding=...)) == "hot"


def test_country_matching_ignores_case_and_spaces():
    assert level(hot_student(target_countries=["  malaysia "])) == "hot"
    assert level(hot_student(target_countries=["canada", "UK"])) == "hot"


@pytest.mark.parametrize("settings", [{}, {"served_countries": []}, {"served_countries": "UK"}])
def test_no_served_countries_setting_blocks_hot(settings):
    assert level(hot_student(), settings) == "warm"


# ---------- study_abroad: dates ----------


@pytest.mark.parametrize(
    "today, intake, expected",
    [
        (datetime.date(2026, 1, 1), "2026-10", "hot"),  # exactly 9 months
        (datetime.date(2025, 12, 31), "2026-10", "warm"),  # 9 months + 1 day
        (datetime.date(2026, 1, 1), "2027-07", "warm"),  # exactly 18 months
        (datetime.date(2025, 12, 31), "2027-07", "cold"),  # 18 months + 1 day
        (datetime.date(2026, 1, 20), "2026-01", "hot"),  # this month: still upcoming
        (datetime.date(2026, 1, 20), "2025-12", "cold"),  # already passed
        (datetime.date(2025, 11, 10), "2026-08", "hot"),  # across the year end (Nov → Aug)
        (datetime.date(2026, 5, 31), "2027-02", "hot"),  # 31st + 9 months = Feb 28
        (datetime.date(2026, 5, 31), "2027-03", "warm"),
        (datetime.date(2027, 5, 31), "2028-02", "hot"),  # leap year: Feb 29
    ],
)
def test_intake_boundaries(today, intake, expected):
    assert level(hot_student(intake=intake), today=today) == expected


@pytest.mark.parametrize("intake", ["2026-9", "2026-13", "Sep 2026", "2026-09-01", 202609, None])
def test_malformed_intake_never_counts(intake):
    assert level(hot_student(intake=intake)) == "cold"


@pytest.mark.parametrize(
    "day, months, expected",
    [
        (datetime.date(2026, 1, 31), 1, datetime.date(2026, 2, 28)),
        (datetime.date(2028, 1, 31), 1, datetime.date(2028, 2, 29)),
        (datetime.date(2026, 11, 30), 3, datetime.date(2027, 2, 28)),
        (datetime.date(2026, 12, 15), 12, datetime.date(2027, 12, 15)),
        (datetime.date(2026, 3, 15), 0, datetime.date(2026, 3, 15)),
    ],
)
def test_add_months(day, months, expected):
    assert _add_months(day, months) == expected


# ---------- study_abroad: Warm, Cold ----------


def test_warm_needs_phone_country_and_intake_within_18_months():
    warm = {"phone": "+8801712345678", "target_countries": ["canada"], "intake": "2027-03"}
    assert level(warm) == "warm"
    for missing in ("phone", "target_countries", "intake"):
        assert level({k: v for k, v in warm.items() if k != missing}) == "cold"


def test_no_phone_is_never_above_cold():
    assert level(hot_student(phone=...)) == "cold"


@pytest.mark.parametrize("profile", [{}, None, "junk", []])
def test_empty_or_junk_profile_is_cold(profile):
    assert score(STUDY, profile, SERVED, TODAY) == Score("cold", ())


# ---------- study_abroad: flags ----------


@pytest.mark.parametrize(
    "changes, flags",
    [
        ({"previous_refusal": "UK 2024"}, ("refusal",)),
        ({"previous_refusal": "  "}, ()),
        ({"study_gap_years": 5}, ("long_gap",)),  # exactly 5
        ({"study_gap_years": 4}, ()),
        ({"study_gap_years": "7"}, ()),  # wrong type: not a number, no flag, no crash
        ({"study_gap_years": True}, ()),  # a bool is not a number of years
        ({"funding": "scholarship_only"}, ("scholarship_only",)),
        (
            {"previous_refusal": "UK", "study_gap_years": 6, "funding": "scholarship_only"},
            ("refusal", "long_gap", "scholarship_only"),  # in the pack's order
        ),
    ],
)
def test_flags(changes, flags):
    assert score(STUDY, hot_student(**changes), SERVED, TODAY).flags == flags


def test_flags_dont_change_the_level():
    assert level(hot_student(previous_refusal="UK 2024", study_gap_years=6)) == "hot"


# ---------- another industry ----------


def test_pet_care_pack_scores_with_the_same_engine():
    settings = {"services_offered": ["grooming", "vaccination"]}
    pet = {
        "phone": "+8801712345678",
        "needs": ["Grooming"],
        "species": "dog",
        "visit_month": "2026-02",
        "vaccinated": False,
        "pet_age_years": 11,
    }
    assert score(PETS, pet, settings, TODAY) == Score("hot", ("not_vaccinated", "senior_pet"))
    parrot = {**pet, "species": "parrot", "pet_age_years": 2, "vaccinated": True}
    assert score(PETS, parrot, settings, TODAY) == Score("warm", ())
    assert score(PETS, {**parrot, "pet_age_years": 10}, settings, TODAY).level == "hot"


# ---------- every generic operator ----------


def rule(**kwargs):
    """A pack whose Hot rule is exactly one condition (warm: never; no flags)."""
    never = Condition(field="missing_field", op="present")
    scoring = Scoring(hot=(Condition(**kwargs),), warm=(never,), flags=())
    return dataclasses.replace(STUDY, scoring=scoring)


def holds(condition_kwargs, value):
    profile = {} if value is ... else {"f": value}
    return score(rule(field="f", **condition_kwargs), profile, {}, TODAY).level == "hot"


@pytest.mark.parametrize(
    "cond, value, expected",
    [
        ({"op": "present"}, "x", True),
        ({"op": "present"}, 0, True),  # zero is a real answer
        ({"op": "present"}, False, True),
        ({"op": "present"}, ..., False),
        ({"op": "present"}, None, False),
        ({"op": "present"}, " ", False),
        ({"op": "present"}, [], False),
        ({"op": "absent"}, ..., True),
        ({"op": "absent"}, "", True),
        ({"op": "absent"}, "x", False),
        ({"op": "eq", "value": "Dog"}, "dog", True),  # text ignores case
        ({"op": "eq", "value": "dog"}, "  DOG ", True),
        ({"op": "eq", "value": "dog"}, "cat", False),
        ({"op": "eq", "value": "dog"}, ..., False),
        ({"op": "eq", "value": 1}, True, False),  # True is not 1
        ({"op": "eq", "value": False}, False, True),
        ({"op": "eq", "value": False}, 0, False),
        ({"op": "eq", "value": 5}, 5, True),
        ({"op": "eq", "value": 10**9}, int("1000000000"), True),  # a separate object: no id luck
        ({"op": "ne", "value": "dog"}, "cat", True),
        ({"op": "ne", "value": "dog"}, "DOG", False),
        ({"op": "ne", "value": "dog"}, ..., True),  # unknown is "not equal"
        ({"op": "in", "values": ("a", "b")}, "B", True),
        ({"op": "in", "values": ("a", "b")}, "c", False),
        ({"op": "in", "values": ("a", "b")}, ..., False),
        ({"op": "not_in", "values": ("a", "b")}, "c", True),
        ({"op": "not_in", "values": ("a", "b")}, "a", False),
        ({"op": "not_in", "values": ("a", "b")}, ..., True),
        ({"op": "gte", "value": 5}, 5, True),
        ({"op": "gte", "value": 5}, 4, False),
        ({"op": "gte", "value": 5}, 5.5, False),  # not an int
        ({"op": "gte", "value": 5}, ..., False),
        ({"op": "lte", "value": 5}, 5, True),
        ({"op": "lte", "value": 5}, 6, False),
        ({"op": "lte", "value": 5}, False, False),
        ({"op": "within_months", "months": 2}, "2026-03", True),
        ({"op": "within_months", "months": 2}, "2026-04", False),
    ],
)
def test_generic_operators(cond, value, expected):
    assert holds(cond, value) is expected


@pytest.mark.parametrize(
    "value, setting, expected",
    [
        (["a"], ["A"], True),
        (("a", "b"), ["b"], True),
        (["a"], ["b"], False),
        ("a", ["a"], False),  # a string is not a list
        (["a"], None, False),
        (["a"], "a", False),
        ([], ["a"], False),
        ([1], [1], True),
        ([True], [1], False),
    ],
)
def test_overlaps_setting(value, setting, expected):
    pack = rule(field="f", op="overlaps_setting", setting="s")
    settings = {} if setting is None else {"s": setting}
    assert (score(pack, {"f": value}, settings, TODAY).level == "hot") is expected


def test_any_holds_when_one_part_holds():
    pack = rule(any=(Condition(field="a", op="present"), Condition(field="b", op="present")))
    assert score(pack, {"b": "x"}, {}, TODAY).level == "hot"
    assert score(pack, {}, {}, TODAY).level == "cold"


def test_flag_needs_all_its_conditions():
    both = (Condition(field="a", op="present"), Condition(field="b", op="present"))
    pack = dataclasses.replace(
        STUDY, scoring=dataclasses.replace(STUDY.scoring, flags=(Flag("ab", both),))
    )
    assert score(pack, {"a": 1, "b": 2}, {}, TODAY).flags == ("ab",)
    assert score(pack, {"a": 1}, {}, TODAY).flags == ()


# ---------- inputs ----------


@pytest.mark.parametrize(
    "today", [datetime.datetime(2026, 1, 15, 10, 0), "2026-01-15", None, 20260115]
)
def test_today_must_be_a_date(today):
    with pytest.raises(TypeError):
        score(STUDY, hot_student(), SERVED, today)


@pytest.mark.parametrize("settings", [None, "junk", []])
def test_junk_settings_dont_raise(settings):
    assert level(hot_student(), settings) == "warm"


def test_scoring_is_pure():
    profile, settings = hot_student(), {"served_countries": ["UK"]}
    before = (dict(profile), dict(settings))
    assert score(STUDY, profile, settings, TODAY) == score(STUDY, profile, settings, TODAY)
    assert (profile, settings) == before


values = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=True),
    st.text(max_size=20),
    st.lists(st.text(max_size=10), max_size=4),
    st.dictionaries(st.text(max_size=5), st.integers(), max_size=2),
)


@given(
    st.dictionaries(st.sampled_from([f.name for f in STUDY.fields] + ["phone"]), values),
    st.dictionaries(st.just("served_countries"), values),
    st.dates(),
)
def test_never_raises_on_any_profile(profile, settings, today):
    result = score(STUDY, profile, settings, today)
    assert result.level in ("hot", "warm", "cold")
    assert set(result.flags) <= {"refusal", "long_gap", "scholarship_only"}


@given(st.dictionaries(st.sampled_from([f.name for f in STUDY.fields]), values))
def test_never_raises_when_every_rule_is_reached(changes):
    # Starting from a Hot profile, rules aren't skipped early, so every check sees the junk.
    result = score(STUDY, {**hot_student(), **changes}, SERVED, TODAY)
    assert result.level in ("hot", "warm", "cold")


@pytest.mark.parametrize("junk", [["ielts"], {"a": 1}, [["uk"]], {"uk"}])
def test_list_or_dict_where_one_value_belongs_matches_nothing(junk):
    assert level(hot_student(english_score=..., english_test=junk)) == "warm"
    assert level(hot_student(target_countries=[junk])) == "warm"
    assert score(STUDY, hot_student(funding=junk), SERVED, TODAY).flags == ()
