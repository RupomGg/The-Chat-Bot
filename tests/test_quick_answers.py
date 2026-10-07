"""Quick answers (P2.2, PRD §6.8, D-015): matching, editing, history and undo."""

import threading

import psycopg
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.quick_answers import (
    MAX_ANSWER,
    MAX_BUTTONS,
    MAX_TRIGGER,
    MAX_TRIGGERS,
    QuickAnswer,
    QuickAnswerError,
    delete_quick_answer,
    find_quick_answer,
    normalize_trigger,
    save_quick_answer,
    undo_change,
)

# ---------- helpers ----------


@pytest.fixture
def conn(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as c:
        yield c


def tenant(conn, slug):
    return conn.execute(
        "INSERT INTO tenants (slug, name, fallback_text) VALUES (%s, 'Acme', 'x') RETURNING id",
        (slug,),
    ).fetchone()[0]


def admin(conn, t, email="admin@x.com"):
    return conn.execute(
        "INSERT INTO users (tenant_id, email, password_hash, role)"
        " VALUES (%s, %s, 'h', 'tenant_admin') RETURNING id",
        (t, email),
    ).fetchone()[0]


@pytest.fixture
def two(conn):
    return tenant(conn, "tenant-a"), tenant(conn, "tenant-b")


def fees(conn, t, **overrides):
    values = {
        "code": "FEES",
        "triggers": ["fees", "koto taka"],
        "answers": {"en": "Counselling is free.", "bn": "কাউন্সেলিং ফ্রি।"},
    }
    return save_quick_answer(conn, t, **{**values, **overrides})


def row(conn, qa_id):
    return conn.execute(
        "SELECT code, triggers, answers, buttons, action, active FROM quick_answers WHERE id = %s",
        (qa_id,),
    ).fetchone()


def history(conn, qa_id):
    return conn.execute(
        "SELECT id, operation, changed_by FROM quick_answer_history"
        " WHERE quick_answer_id = %s ORDER BY id",
        (qa_id,),
    ).fetchall()


def history_count(conn):
    return conn.execute("SELECT count(*) FROM quick_answer_history").fetchone()[0]


def last_change(conn, qa_id):
    return history(conn, qa_id)[-1][0]


# ---------- normalize_trigger ----------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("fees", "fees"),
        ("Fees??", "fees"),
        ("  Office   kothay? ", "office kothay"),
        ("IELTS lagbe?", "ielts lagbe"),
        ("ঠিকানা।", "ঠিকানা"),  # Bangla full stop (danda) stripped
        ("FEES 💰", "fees"),  # emoji stripped
        ("what's the fee", "what s the fee"),  # punctuation becomes a space, both sides agree
        ("fees/cost", "fees cost"),
        ("ＦＥＥＳ", "fees"),  # full-width letters
        ("Straße", "strasse"),
        ("২০২৭ intake", "২০২৭ intake"),  # Bangla digits kept
        ("uk\tfees\nplease", "uk fees please"),
        ("ক্\u200dষ", "ক্ষ"),  # Bangla joiner ignored: typed inconsistently
        ("ক্\u200cষ", "ক্ষ"),
        ("e\u0301", "é"),  # decomposed accent composed, same as typing é
        ("x" * MAX_TRIGGER, "x" * MAX_TRIGGER),
    ],
)
def test_normalize_trigger(text, expected):
    assert normalize_trigger(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "???",
        "💰💰",
        "।",
        "\u200d",
        "x" * (MAX_TRIGGER + 1),
        "a " * 1000,  # long student message: no trigger can be that long
        None,
        5,
        b"fees",
        ["fees"],
    ],
)
def test_normalize_trigger_rejects(text):
    assert normalize_trigger(text) is None


@given(st.text(max_size=300))
def test_normalize_trigger_never_raises_and_is_stable(text):
    result = normalize_trigger(text)
    if result is not None:
        assert normalize_trigger(result) == result
        assert result == result.strip()
        assert "  " not in result
        assert 1 <= len(result) <= MAX_TRIGGER
        assert result == result.lower()  # the database's rule, checked on every OS


@pytest.mark.parametrize("upper", [chr(0x13A0), chr(0x13F5), chr(0x13A0) + chr(0x13A1)])
def test_cherokee_ends_up_lower_case(upper):
    # casefold() maps Cherokee to UPPER case; Linux/macOS databases then rejected it (CI #5).
    result = normalize_trigger(upper)
    assert result == upper.lower() != upper
    assert normalize_trigger(result) == result


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])  # read-only use
@given(st.text(max_size=120))
def test_normalized_triggers_satisfy_the_database_rule(conn, text):
    # The database checks triggers with its own lower() and btrim(); Python must agree.
    result = normalize_trigger(text)
    if result is not None:
        ok = conn.execute("SELECT quick_answer_triggers_ok(ARRAY[%s])", (result,)).fetchone()[0]
        assert ok, repr(result)


@pytest.mark.parametrize("text", ["İstanbul", "ΣΊΣΥΦΟΣ", "ǅemal", "ﬁnance", "Ⅻ", "ẞ", "K"])
def test_tricky_letters_satisfy_the_database_rule(conn, text):
    result = normalize_trigger(text)
    assert result
    assert conn.execute("SELECT quick_answer_triggers_ok(ARRAY[%s])", (result,)).fetchone()[0]


# ---------- find_quick_answer ----------


def test_button_payload_finds_by_exact_code(conn, two):
    a, _ = two
    qa_id = fees(conn, a, buttons=[], action=None)
    found = find_quick_answer(conn, a, payload="FEES", language="en")
    assert found == QuickAnswer(qa_id, "FEES", "Counselling is free.", "en", (), None)


def test_typed_text_finds_by_normalized_trigger(conn, two):
    a, _ = two
    fees(conn, a)
    for typed in ("fees", "FEES?", "  Koto   taka!! ", "koto taka 💰"):
        assert find_quick_answer(conn, a, text=typed).code == "FEES"


def office(conn, t, **overrides):
    values = {
        "code": "OFFICE",
        "triggers": ["address", "office kothay", "ঠিকানা", "location"],
        "answers": {"en": "House 5, Banani."},
    }
    return save_quick_answer(conn, t, **{**values, **overrides})


# The owner's phone check (D-025): typos and question words around a trigger still match.
@pytest.mark.parametrize(
    "typed, code",
    [
        ("fee", "FEES"),
        ("fess", "FEES"),
        ("feees", "FEES"),
        ("fees please", "FEES"),
        ("what are the fees", "FEES"),
        ("apnader fee koto?", "FEES"),
        ("taka", "FEES"),  # "koto taka" less its question word
        ("address kothay", "OFFICE"),
        ("where is your address?", "OFFICE"),
        ("adresss", "OFFICE"),
        ("adddress koi", "OFFICE"),
        ("address ki", "OFFICE"),
        ("addres kothai", "OFFICE"),
        ("office", "OFFICE"),
        ("ofice kothay", "OFFICE"),
        ("ঠিকানা কোথায়", "OFFICE"),
        # real typos, not just doubled letters: one wrong, extra or missing letter in a word of
        # 4-6 letters ("ofice"), up to two in a longer one ("location")
        ("ofise kothay", "OFFICE"),
        ("ofixce", "OFFICE"),
        ("ofce", "OFFICE"),
        ("adr koi", "OFFICE"),
        ("locasion", "OFFICE"),
        ("lokasion", "OFFICE"),
        ("আপনাদের ঠিকানা কি", "OFFICE"),
    ],
)
def test_typos_and_question_words_still_match(conn, two, typed, code):
    a, _ = two
    fees(conn, a)
    office(conn, a)
    assert find_quick_answer(conn, a, text=typed).code == code


@pytest.mark.parametrize(
    "typed",
    [
        "",
        "where is",  # only question words
        "kototaka",  # one word that isn't a trigger
        "fees for UK",  # more than the trigger: the AI answers
        "address of oxford university",
        "feed",  # short words must be exact: "fe" vs "fed"
        "free",
        "box",
        "adrs xyz",
        "ofxyz",  # two letters off a 5-letter word
        "lokasyon",  # three letters off an 8-letter word
    ],
)
def test_other_text_doesnt_match(conn, two, typed):
    a, _ = two
    fees(conn, a)
    office(conn, a)
    save_quick_answer(conn, a, code="BOOK", triggers=["book"], action="start_booking")
    assert find_quick_answer(conn, a, text=typed) is None


def test_longer_numbers_must_match_exactly_too(conn, two):
    a, _ = two
    save_quick_answer(conn, a, code="JAN", triggers=["intake 2027"], answers={"en": "Open."})
    assert find_quick_answer(conn, a, text="intake 2027 ki").code == "JAN"
    assert find_quick_answer(conn, a, text="intake 2026") is None  # one digit off is not a typo


@pytest.mark.parametrize("typed", ["ielts 6", "ielts 7 5", "ielts 6 0"])
def test_numbers_must_match_exactly(conn, two, typed):  # PRD §20: "IELTS 6" isn't "IELTS 6.5"
    a, _ = two
    save_quick_answer(conn, a, code="IELTS", triggers=["ielts 6.5"], answers={"en": "Yes."})
    assert find_quick_answer(conn, a, text="ielts 6.5?").code == "IELTS"
    assert find_quick_answer(conn, a, text="ieltss 6.5").code == "IELTS"
    assert find_quick_answer(conn, a, text=typed) is None


def test_two_answers_that_both_fit_mean_neither(conn, two):
    a, _ = two
    office(conn, a)
    save_quick_answer(conn, a, code="BRANCH", triggers=["adres"], answers={"en": "Two."})
    assert find_quick_answer(conn, a, text="addresss") is None  # fits both: the AI answers
    assert find_quick_answer(conn, a, text="adres").code == "BRANCH"  # exact still wins


def test_an_exact_trigger_beats_a_forgiving_match(conn, two):
    a, _ = two
    fees(conn, a)
    save_quick_answer(conn, a, code="PRICE", triggers=["fee"], answers={"en": "Price list."})
    assert find_quick_answer(conn, a, text="fee").code == "PRICE"


def test_forgiving_match_skips_switched_off_and_other_companies(conn, two):
    a, b = two
    office(conn, b)
    office(conn, a, active=False)
    assert find_quick_answer(conn, a, text="address kothay") is None
    assert find_quick_answer(conn, b, text="address kothay").code == "OFFICE"


def test_a_trigger_of_only_question_words_never_matches(conn, two):
    a, _ = two
    save_quick_answer(conn, a, code="HUH", triggers=["kothay"], answers={"en": "?"})
    assert find_quick_answer(conn, a, text="kothay").code == "HUH"  # exact is fine
    assert find_quick_answer(conn, a, text="kothai") is None


@pytest.mark.parametrize("payload", ["fees", "NOPE", "F", "FEES ", "X" * 41, 5, b"FEES", ""])
def test_junk_or_unknown_payload_doesnt_match(conn, two, payload):
    a, _ = two
    fees(conn, a)
    assert find_quick_answer(conn, a, payload=payload) is None


def test_inactive_answers_are_ignored(conn, two):
    a, _ = two
    fees(conn, a, active=False)
    assert find_quick_answer(conn, a, payload="FEES") is None
    assert find_quick_answer(conn, a, text="fees") is None


def test_another_tenants_answer_is_never_returned(conn, two):
    a, b = two
    fees(conn, a, answers={"en": "A's fees"})
    assert find_quick_answer(conn, b, payload="FEES") is None
    assert find_quick_answer(conn, b, text="fees") is None
    fees(conn, b, answers={"en": "B's fees"})  # same code and trigger in another company
    assert find_quick_answer(conn, a, text="fees").text == "A's fees"
    assert find_quick_answer(conn, b, text="fees").text == "B's fees"


@pytest.mark.parametrize(
    "answers, language, expected",
    [
        ({"en": "E", "bn": "B"}, "bn", ("B", "bn")),
        ({"en": "E", "bn": "B"}, "en", ("E", "en")),
        ({"en": "E", "bn": "B"}, "fr", ("E", "en")),  # not available → English
        ({"bn": "B", "hi": "H"}, "fr", ("B", "bn")),  # no English → first available
        ({"hi": "H", "bn": "B"}, "en", ("B", "bn")),  # "first" is alphabetical: stable
        ({"en": "E"}, None, ("E", "en")),
        ({"en": "E", "bn": "B"}, ["bn"], ("E", "en")),  # junk language → English
    ],
)
def test_language_fallback(conn, two, answers, language, expected):
    a, _ = two
    fees(conn, a, answers=answers)
    found = find_quick_answer(conn, a, payload="FEES", language=language)
    assert (found.text, found.language) == expected


def test_action_only_answer(conn, two):
    a, _ = two
    save_quick_answer(conn, a, code="BOOK", triggers=["book"], action="start_booking")
    found = find_quick_answer(conn, a, text="Book!")
    assert (found.text, found.language, found.action) == (None, None, "start_booking")


def test_follow_up_buttons_are_returned_in_order(conn, two):
    a, _ = two
    save_quick_answer(conn, a, code="UK", answers={"en": "UK"})
    save_quick_answer(conn, a, code="CANADA", answers={"en": "CA"})
    fees(conn, a, buttons=["UK", "CANADA"])
    assert find_quick_answer(conn, a, payload="FEES").buttons == ("UK", "CANADA")


@pytest.mark.parametrize("kwargs", [{}, {"payload": "FEES", "text": "fees"}])
def test_exactly_one_of_payload_or_text(conn, two, kwargs):
    with pytest.raises(TypeError):
        find_quick_answer(conn, two[0], **kwargs)


# ---------- save_quick_answer ----------


def test_save_creates_normalized_answer(conn, two):
    a, _ = two
    qa_id = save_quick_answer(
        conn,
        a,
        code=" fees_uk ",
        triggers=["UK Fees?", "  ইউকে   খরচ। "],
        answers={"en": "  Line 1\r\nLine 2  ", "bn": "টিউশন"},
    )
    assert row(conn, qa_id) == (
        "FEES_UK",
        ["uk fees", "ইউকে খরচ"],
        {"en": "Line 1\nLine 2", "bn": "টিউশন"},
        [],
        None,
        True,
    )


def test_save_goes_live_immediately(conn, two):
    a, _ = two
    fees(conn, a)
    assert find_quick_answer(conn, a, text="fees") is not None


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"code": "fees uk"}, "code 'fees uk'"),
        ({"code": "F"}, "code 'F'"),
        ({"code": None}, "code None"),
        ({"code": "1FEES"}, "code '1FEES'"),
        ({"triggers": ["💰"]}, "trigger '💰': needs letters or numbers"),
        ({"triggers": ["x" * (MAX_TRIGGER + 1)]}, "at most 100 characters"),
        ({"triggers": ["Fees", "fees?"]}, "triggers 'Fees' and 'fees?' are the same phrase"),
        ({"triggers": "fees"}, "triggers must be a list"),
        ({"triggers": None}, "triggers must be a list"),
        ({"triggers": [f"t{i}" for i in range(MAX_TRIGGERS + 1)]}, "at most 50 triggers"),
        ({"answers": "Free"}, "answers must map a language code"),
        ({"answers": {"english": "Free"}}, "answer language 'english'"),
        ({"answers": {"EN": "Free"}}, "answer language 'EN'"),
        ({"answers": {1: "Free"}}, "answer language 1"),
        ({"answers": {"en": 5}}, "answer en: must be text"),
        ({"answers": {"en": "   "}}, "answer en: empty"),
        ({"answers": {"en": "x" * (MAX_ANSWER + 1)}}, "answer en: at most 2000 characters"),
        ({"answers": {"en": "bell\x07"}}, "answer en: contains control characters"),
        ({"buttons": "UK"}, "buttons must be a list"),
        ({"buttons": ["A1", "A2", "A3", "A4"]}, "at most 3 buttons"),
        ({"buttons": ["uk fees"]}, "button 'uk fees': not a valid"),
        ({"buttons": [None]}, "button None: not a valid"),
        ({"buttons": ["FEES", "fees"]}, "button FEES is listed twice"),
        ({"action": "call_mom"}, "action 'call_mom'"),
        ({"active": "yes"}, "active must be true or false"),
        ({"answers": {}}, "needs an answer in at least one language, or an action"),
        ({"answers": None}, "needs an answer in at least one language, or an action"),
    ],
)
def test_save_rejects_invalid(conn, two, overrides, message):
    with pytest.raises(QuickAnswerError, match=None) as caught:
        fees(conn, two[0], **overrides)
    assert message in str(caught.value)
    assert history_count(conn) == 0  # nothing reached the database


def test_save_lists_every_problem_at_once(conn, two):
    with pytest.raises(QuickAnswerError) as caught:
        save_quick_answer(conn, two[0], code="x", triggers=["💰"], answers={"EN": "a"})
    assert str(caught.value).count(";") == 2


def test_boundaries_accepted(conn, two):
    a, _ = two
    qa_id = fees(
        conn,
        a,
        triggers=[f"t{i}" for i in range(MAX_TRIGGERS)],
        answers={"en": "x" * MAX_ANSWER, "bn": "tab\there\nnewline"},
    )
    assert len(row(conn, qa_id)[1]) == MAX_TRIGGERS


def test_buttons_must_point_at_existing_answers(conn, two):
    a, b = two
    save_quick_answer(conn, b, code="UK", answers={"en": "B's UK"})  # other company's: no
    with pytest.raises(QuickAnswerError, match="button UK, CANADA: no such quick answer"):
        fees(conn, a, buttons=["UK", "CANADA"])
    assert history_count(conn) == 1  # only b's answer


def test_buttons_may_include_itself_and_max_count(conn, two):
    a, _ = two
    save_quick_answer(conn, a, code="UK", answers={"en": "UK"})
    save_quick_answer(conn, a, code="CANADA", answers={"en": "CA"})
    qa_id = fees(conn, a, buttons=["uk", "CANADA", "FEES"])  # "more fees info" loop is fine
    assert row(conn, qa_id)[3] == ["UK", "CANADA", "FEES"]
    assert MAX_BUTTONS == 3


def test_trigger_clash_with_another_answer_is_friendly(conn, two):
    a, _ = two
    fees(conn, a)
    with pytest.raises(QuickAnswerError, match='trigger "koto taka" already belongs'):
        save_quick_answer(conn, a, code="PRICE", triggers=["Koto Taka?"], answers={"en": "x"})


def test_duplicate_code_is_friendly(conn, two):
    a, _ = two
    fees(conn, a)
    with pytest.raises(QuickAnswerError, match="code FEES already exists for this company"):
        fees(conn, a, triggers=["other"])


def test_same_code_and_trigger_in_two_companies(conn, two):
    a, b = two
    assert fees(conn, a) != fees(conn, b)


def test_update_replaces_fields(conn, two):
    a, _ = two
    qa_id = fees(conn, a)
    same = save_quick_answer(
        conn,
        a,
        quick_answer_id=qa_id,
        code="FEES",
        triggers=["fees", "cost"],  # keeps its own trigger: not a clash with itself
        answers={"en": "Free for students."},
        active=False,
    )
    assert same == qa_id
    assert row(conn, qa_id) == (
        "FEES",
        ["fees", "cost"],
        {"en": "Free for students."},
        [],
        None,
        False,
    )


def test_update_can_rename_code(conn, two):
    a, _ = two
    qa_id = fees(conn, a)
    fees(conn, a, quick_answer_id=qa_id, code="FEES_ALL")
    assert find_quick_answer(conn, a, payload="FEES_ALL").id == qa_id
    assert find_quick_answer(conn, a, payload="FEES") is None


def test_update_of_another_tenants_answer_is_refused(conn, two):
    a, b = two
    qa_id = fees(conn, a)
    with pytest.raises(QuickAnswerError, match="quick answer not found"):
        fees(conn, b, quick_answer_id=qa_id, answers={"en": "hijacked"})
    assert row(conn, qa_id)[2]["en"] == "Counselling is free."


def test_update_of_missing_answer(conn, two):
    with pytest.raises(QuickAnswerError, match="quick answer not found"):
        fees(conn, two[0], quick_answer_id=999_999)


def test_history_records_who(conn, two):
    a, _ = two
    user = admin(conn, a)
    qa_id = fees(conn, a, user_id=user)
    fees(conn, a, quick_answer_id=qa_id, answers={"en": "New"})  # system (no user)
    assert [(op, by) for _, op, by in history(conn, qa_id)] == [
        ("insert", user),
        ("update", None),
    ]


def test_user_setting_doesnt_leak_into_later_changes(conn, two):
    a, _ = two
    user = admin(conn, a)
    fees(conn, a, user_id=user)
    other = save_quick_answer(conn, a, code="UK", answers={"en": "UK"})
    assert history(conn, other)[0][2] is None


@pytest.mark.parametrize("user_id", [True, "5", 1.0])
def test_user_id_must_be_an_int(conn, two, user_id):
    with pytest.raises(TypeError):
        fees(conn, two[0], user_id=user_id)


def test_unknown_user_is_refused_by_the_database(conn, two):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        fees(conn, two[0], user_id=999_999)
    assert history_count(conn) == 0


def test_save_inside_callers_transaction_rolls_back_with_it(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as setup:
        a = tenant(setup, "tenant-a")
    with psycopg.connect(migrated_db_url) as c:
        c.execute("SELECT 1")  # the caller's transaction is already open
        fees(c, a)
        c.rollback()
        assert find_quick_answer(c, a, payload="FEES") is None


def test_save_on_an_idle_connection_commits_by_itself(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as setup:
        a = tenant(setup, "tenant-a")
    with psycopg.connect(migrated_db_url) as c:  # not autocommit, no transaction open yet
        fees(c, a)
        c.rollback()  # nothing to roll back: the save was already committed
        assert find_quick_answer(c, a, payload="FEES") is not None


# ---------- delete_quick_answer ----------


def test_delete(conn, two):
    a, _ = two
    user = admin(conn, a)
    qa_id = fees(conn, a)
    delete_quick_answer(conn, a, qa_id, user_id=user)
    assert row(conn, qa_id) is None
    assert find_quick_answer(conn, a, text="fees") is None
    assert history(conn, qa_id)[-1][1:] == ("delete", user)


def test_delete_another_tenants_answer_is_refused(conn, two):
    a, b = two
    qa_id = fees(conn, a)
    with pytest.raises(QuickAnswerError, match="quick answer not found"):
        delete_quick_answer(conn, b, qa_id)
    assert row(conn, qa_id) is not None


def test_delete_missing(conn, two):
    with pytest.raises(QuickAnswerError, match="quick answer not found"):
        delete_quick_answer(conn, two[0], 999_999)


def test_deleted_answer_frees_its_triggers_and_code(conn, two):
    a, _ = two
    delete_quick_answer(conn, a, fees(conn, a))
    assert fees(conn, a)


def test_button_to_a_deleted_answer_just_stops_matching(conn, two):
    a, _ = two
    uk = save_quick_answer(conn, a, code="UK", answers={"en": "UK"})
    fees(conn, a, buttons=["UK"])
    delete_quick_answer(conn, a, uk)
    assert find_quick_answer(conn, a, payload="UK") is None  # the AI answers instead


# ---------- undo_change ----------


def test_undo_create_deletes_it(conn, two):
    a, _ = two
    qa_id = fees(conn, a)
    assert undo_change(conn, a, last_change(conn, qa_id)) == qa_id
    assert row(conn, qa_id) is None


def test_undo_edit_restores_previous_version(conn, two):
    a, _ = two
    qa_id = fees(conn, a)
    before = row(conn, qa_id)
    fees(conn, a, quick_answer_id=qa_id, code="PRICE", triggers=["price"], active=False)
    undo_change(conn, a, last_change(conn, qa_id))
    assert row(conn, qa_id) == before
    assert find_quick_answer(conn, a, text="koto taka").id == qa_id


def test_undo_delete_recreates_it_with_the_same_id(conn, two):
    a, _ = two
    uk = save_quick_answer(conn, a, code="UK", answers={"en": "UK"})
    qa_id = fees(conn, a, buttons=["UK"], action="start_booking")
    before = row(conn, qa_id)
    delete_quick_answer(conn, a, qa_id)
    assert undo_change(conn, a, last_change(conn, qa_id)) == qa_id
    assert row(conn, qa_id) == before
    assert find_quick_answer(conn, a, payload="FEES").buttons == ("UK",)
    assert uk != qa_id


def test_undo_is_recorded_with_who(conn, two):
    a, _ = two
    user = admin(conn, a)
    qa_id = fees(conn, a)
    delete_quick_answer(conn, a, qa_id)
    undo_change(conn, a, last_change(conn, qa_id), user_id=user)
    assert history(conn, qa_id)[-1][1:] == ("insert", user)


def test_undo_twice_is_refused(conn, two):
    a, _ = two
    qa_id = fees(conn, a)
    fees(conn, a, quick_answer_id=qa_id, answers={"en": "New"})
    change = last_change(conn, qa_id)
    undo_change(conn, a, change)
    with pytest.raises(QuickAnswerError, match="changed again after that"):
        undo_change(conn, a, change)
    assert row(conn, qa_id)[2]["en"] == "Counselling is free."


def test_undo_of_an_undo_redoes(conn, two):
    a, _ = two
    qa_id = fees(conn, a)
    delete_quick_answer(conn, a, qa_id)
    undo_change(conn, a, last_change(conn, qa_id))  # back
    undo_change(conn, a, last_change(conn, qa_id))  # deleted again
    assert row(conn, qa_id) is None


def test_undo_of_an_older_change_is_refused(conn, two):
    a, _ = two
    qa_id = fees(conn, a)
    first_edit_before = last_change(conn, qa_id)
    fees(conn, a, quick_answer_id=qa_id, answers={"en": "Second"})
    with pytest.raises(QuickAnswerError, match="undo the newer change first"):
        undo_change(conn, a, first_edit_before)
    assert row(conn, qa_id)[2] == {"en": "Second"}


def test_undo_of_another_tenants_change_is_refused(conn, two):
    a, b = two
    qa_id = fees(conn, a)
    with pytest.raises(QuickAnswerError, match="change not found"):
        undo_change(conn, b, last_change(conn, qa_id))
    assert row(conn, qa_id) is not None


def test_undo_missing_change(conn, two):
    with pytest.raises(QuickAnswerError, match="change not found"):
        undo_change(conn, two[0], 999_999)


def test_undo_delete_when_trigger_was_taken_since(conn, two):
    a, _ = two
    qa_id = fees(conn, a)
    delete_quick_answer(conn, a, qa_id)
    save_quick_answer(conn, a, code="PRICE", triggers=["fees"], answers={"en": "x"})
    with pytest.raises(QuickAnswerError, match='trigger "fees" already belongs'):
        undo_change(conn, a, last_change(conn, qa_id))
    assert row(conn, qa_id) is None


def test_undo_delete_when_code_was_reused_since(conn, two):
    a, _ = two
    qa_id = fees(conn, a)
    delete_quick_answer(conn, a, qa_id)
    fees(conn, a, triggers=["other"])
    with pytest.raises(QuickAnswerError, match="code FEES already exists"):
        undo_change(conn, a, last_change(conn, qa_id))


def test_undo_edit_when_old_trigger_was_taken_since(conn, two):
    a, _ = two
    qa_id = fees(conn, a)
    fees(conn, a, quick_answer_id=qa_id, triggers=["fees"])  # drops "koto taka"
    save_quick_answer(conn, a, code="PRICE", triggers=["koto taka"], answers={"en": "x"})
    with pytest.raises(QuickAnswerError, match='trigger "koto taka" already belongs'):
        undo_change(conn, a, last_change(conn, qa_id))
    assert row(conn, qa_id)[1] == ["fees"]


def test_two_admins_undoing_the_same_change_at_once(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as setup:
        a = tenant(setup, "tenant-a")
        qa_id = fees(setup, a)
        fees(setup, a, quick_answer_id=qa_id, answers={"en": "New"})
        change = last_change(setup, qa_id)
    first = psycopg.connect(migrated_db_url)  # holds its transaction open
    second = psycopg.connect(migrated_db_url, autocommit=True)
    outcome = {}
    try:
        first.execute("SELECT 1")  # open transaction: the undo commits only with it
        undo_change(first, a, change)

        def other_admin():
            try:
                undo_change(second, a, change)
                outcome["second"] = "undone"
            except QuickAnswerError as error:
                outcome["second"] = str(error)

        worker = threading.Thread(target=other_admin)
        worker.start()
        worker.join(timeout=1)
        assert worker.is_alive()  # waits for the first admin's undo
        first.commit()
        worker.join(timeout=10)
        assert "changed again after that" in outcome["second"]
    finally:
        first.close()
        second.close()
