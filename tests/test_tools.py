"""The AI's tools (P4.3, PRD §9.4, D-014, D-020)."""

import datetime
import pathlib
import zoneinfo

import psycopg
import pytest

from app.llm import ToolCall
from app.packs import CORE_HANDOFF_REASONS, load_pack
from app.tools import ToolContext, ToolResult, result_block, run, schemas

UTC = datetime.UTC
DHAKA = zoneinfo.ZoneInfo("Asia/Dhaka")
NOW = datetime.datetime(2026, 10, 4, 12, 0, tzinfo=DHAKA)  # a Sunday
MONDAY_10 = datetime.datetime(2026, 10, 5, 10, 0, tzinfo=DHAKA)
STUDY = load_pack("study_abroad")
PETS = load_pack("pet_care_sample", pathlib.Path(__file__).parent / "fixtures" / "packs")


# ---------- setup ----------


def one(conn, query, params=()):
    return conn.execute(query, params).fetchone()[0]


class World:
    """A company (Dhaka) with a branch open Mondays 10-12 (1 seat per slot), a contact and a
    conversation; plus a second company with its own contact, branch and event."""

    def __init__(self, conn):
        self.conn = conn
        self.tenant = self._company("acme")
        self.branch = one(
            conn,
            "INSERT INTO branches (tenant_id, name) VALUES (%s, 'Banani') RETURNING id",
            (self.tenant,),
        )
        conn.execute(
            "INSERT INTO schedules (tenant_id, branch_id, weekday, start_time, end_time,"
            " slot_minutes, capacity) VALUES (%s, %s, 1, '10:00', '12:00', 60, 1)",
            (self.tenant, self.branch),
        )
        self.contact, self.conversation = self._person(self.tenant, "u1")
        self.other_tenant = self._company("other")
        self.other_contact, self.other_conversation = self._person(self.other_tenant, "u9")
        self.other_branch = one(
            conn,
            "INSERT INTO branches (tenant_id, name) VALUES (%s, 'Elsewhere') RETURNING id",
            (self.other_tenant,),
        )

    def _company(self, slug):
        return one(
            self.conn,
            "INSERT INTO tenants (slug, name, fallback_text) VALUES (%s, 'A', 'x') RETURNING id",
            (slug,),
        )

    def _person(self, tenant, ext):
        found = self.conn.execute(
            "SELECT id FROM channels WHERE tenant_id = %s", (tenant,)
        ).fetchone()  # one web channel per company
        ch = (
            found[0]
            if found
            else one(
                self.conn,
                "INSERT INTO channels (tenant_id, type) VALUES (%s, 'web') RETURNING id",
                (tenant,),
            )
        )
        contact = one(
            self.conn,
            "INSERT INTO contacts (tenant_id, channel_id, external_user_id)"
            " VALUES (%s, %s, %s) RETURNING id",
            (tenant, ch, ext),
        )
        conversation = one(
            self.conn,
            "INSERT INTO conversations (tenant_id, contact_id) VALUES (%s, %s) RETURNING id",
            (tenant, contact),
        )
        return contact, conversation

    def ctx(self, **overrides):
        args = {
            "conn": self.conn,
            "tenant_id": self.tenant,
            "contact_id": self.contact,
            "conversation_id": self.conversation,
            "pack": STUDY,
            "settings": {"served_countries": ["uk"]},
            "now": NOW,
            "timezone": "Asia/Dhaka",
        }
        return ToolContext(**(args | overrides))

    def contact_row(self, contact=None):
        return self.conn.execute(
            "SELECT name, phone, email, adult, profile, score, flags, status FROM contacts"
            " WHERE id = %s",
            (contact or self.contact,),
        ).fetchone()

    def events(self, kind):
        return self.conn.execute(
            "SELECT detail FROM audit_events WHERE kind = %s ORDER BY id", (kind,)
        ).fetchall()


@pytest.fixture
def world(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as conn:
        yield World(conn)


def use(world, name, args, **ctx):
    return run(world.ctx(**ctx), ToolCall("t1", name, args))


# ---------- schemas ----------


def all_objects(schema):
    if schema.get("type") == "object":
        yield schema
        for prop in schema["properties"].values():
            yield from all_objects(prop)
    if schema.get("type") == "array":
        yield from all_objects(schema["items"])


@pytest.mark.parametrize("pack", [STUDY, PETS])
def test_every_schema_is_strict(pack):
    tools = schemas(pack)
    assert [t["name"] for t in tools] == [
        "update_profile",
        "list_slots",
        "book_appointment",
        "register_event",
        "log_unanswered",
        "off_topic",
        "request_handoff",
    ]
    for tool in tools:
        assert tool["strict"] is True
        for obj in all_objects(tool["input_schema"]):
            assert obj["additionalProperties"] is False
            assert set(obj["required"]) <= set(obj["properties"])
        text = str(tool["input_schema"])
        for unsupported in ("minimum", "maximum", "minLength", "maxLength"):
            assert unsupported not in text  # strict mode doesn't support them
        for scope in ("contact_id", "tenant_id", "conversation_id"):
            assert scope not in text  # the AI can never name another contact


def test_profile_schema_follows_the_pack():
    props = schemas(STUDY)[0]["input_schema"]["properties"]
    assert set(props) == {f.name for f in STUDY.fields} | {"name", "phone", "email", "adult"}
    assert props["english_test"]["enum"] == list(STUDY.fields[2].choices)
    assert props["intake"]["description"] == "Intake (YYYY-MM)"
    assert props["target_countries"] == {
        "type": "array",
        "items": {"type": "string"},
        "description": "Target countries",
    }
    assert props["study_gap_years"]["type"] == "integer"


def test_handoff_reasons_are_core_plus_the_pack():
    study = schemas(STUDY)[-1]["input_schema"]["properties"]["reason"]["enum"]
    pets = schemas(PETS)[-1]["input_schema"]["properties"]["reason"]["enum"]
    assert study == [*CORE_HANDOFF_REASONS, "visa_case", "fee_dispute"]
    assert pets == list(CORE_HANDOFF_REASONS)


def test_descriptions_use_the_industry_words():
    assert "counselling session" in schemas(STUDY)[1]["description"]
    assert "vet visit" in schemas(PETS)[2]["description"]


# ---------- running calls ----------


def test_unknown_tool(world):
    assert use(world, "delete_everything", {}).content == {
        "error": "unknown tool 'delete_everything'"
    }


def test_input_given_as_json_text(world):
    assert use(world, "update_profile", '{"study_gap_years": 2}').content == {
        "saved": ["study_gap_years"]
    }


@pytest.mark.parametrize(
    "args, message",
    [
        ("{not json", "input is not valid JSON"),
        ("[1, 2]", "input must be a JSON object"),
        (["x"], "input must be a JSON object"),
        (None, "input must be a JSON object"),
    ],
)
def test_bad_input_is_an_error_result_not_an_exception(world, args, message):
    result = use(world, "update_profile", args)
    assert result.is_error and result.content == {"error": message}


# ---------- update_profile ----------


def test_empty_update_is_a_no_op(world):
    before = world.contact_row()
    assert use(world, "update_profile", {}) == ToolResult({"saved": []})
    assert world.contact_row() == before


def test_profile_values_are_cleaned_and_stored(world):
    result = use(
        world,
        "update_profile",
        {
            "name": "  rahim   uddin ",
            "phone": "01712 345-678",
            "email": "Rahim@GMAIL.com",
            "intake": "Jan 2027",
            "english_test": " IELTS ",
            "target_countries": ["UK", "uk ", " Canada"],
            "study_gap_years": 3,
            "subject": "  Computer   Science ",
        },
    )
    assert not result.is_error
    assert result.content["saved"] == sorted(
        [
            "name",
            "phone",
            "email",
            "intake",
            "english_test",
            "target_countries",
            "study_gap_years",
            "subject",
        ]
    )
    name, phone, email, _, profile, *_ = world.contact_row()
    assert (name, phone, email) == ("rahim uddin", "+8801712345678", "Rahim@gmail.com")
    assert profile == {
        "intake": "2027-01",
        "english_test": "ielts",
        "target_countries": ["UK", "Canada"],
        "study_gap_years": 3,
        "subject": "Computer Science",
    }


def test_updates_merge_with_what_was_saved_before(world):
    use(world, "update_profile", {"subject": "CSE"})
    use(world, "update_profile", {"study_gap_years": 1})
    assert world.contact_row()[4] == {"subject": "CSE", "study_gap_years": 1}


def test_under_18_phone_is_stored(world):
    # D-014: adult = false is recorded and the phone is still kept.
    assert not use(world, "update_profile", {"adult": False, "phone": "01812345678"}).is_error
    assert world.contact_row()[1:4] == ("+8801812345678", None, False)


@pytest.mark.parametrize(
    "args, message",
    [
        ({"phone": "12345"}, "phone: not a valid phone number"),
        ({"phone": 1712345678}, "phone: not a valid phone number"),
        ({"email": "rahim@"}, "email: not a valid email address"),
        ({"name": "12345"}, "name: not a name"),
        ({"adult": "yes"}, "adult: must be true or false"),
        ({"english_test": "gre"}, "english_test: must be one of: ielts, pte"),
        ({"study_gap_years": True}, "study_gap_years: must be a whole number"),
        ({"study_gap_years": -1}, "study_gap_years: must be a whole number"),
        ({"study_gap_years": 1001}, "study_gap_years: must be a whole number"),
        ({"intake": "someday"}, "intake: must be a month like 2027-01"),
        ({"subject": "   "}, "subject: must be non-empty text"),
        ({"target_countries": "UK"}, "target_countries: must be a list of up to 20 items"),
        ({"target_countries": ["x"] * 21}, "target_countries: must be a list of up to 20 items"),
        ({"target_countries": ["UK", ""]}, "target_countries: must be non-empty text"),
    ],
)
def test_invalid_values_are_explained(world, args, message):
    result = use(world, "update_profile", args)
    assert result.is_error
    assert message in result.content["error"]
    assert result.content["error"].startswith("nothing saved; fix: ")


def test_one_bad_value_saves_nothing(world):
    result = use(world, "update_profile", {"intake": "2027-01", "phone": "123"})
    assert result.is_error
    assert world.contact_row()[4] == {}  # the good intake wasn't saved either
    assert world.contact_row()[1] is None


def test_every_problem_is_listed_at_once(world):
    error = use(world, "update_profile", {"phone": "1", "intake": "x"}).content["error"]
    assert "phone:" in error and "intake:" in error


def test_unknown_fields_are_rejected(world):
    result = use(world, "update_profile", {"favourite_colour": "blue", "intake": "2027-01"})
    assert result.content == {"error": "unknown field(s): favourite_colour"}
    assert world.contact_row()[4] == {}


def test_another_contacts_id_never_reaches_them(world):
    before = world.contact_row(world.other_contact)
    result = use(world, "update_profile", {"contact_id": world.other_contact, "name": "Hacker"})
    assert result.content == {"error": "unknown field(s): contact_id"}
    assert world.contact_row(world.other_contact) == before


def test_boolean_pack_field(world):
    ctx = {"pack": PETS, "settings": {}}
    assert not use(world, "update_profile", {"vaccinated": True}, **ctx).is_error
    assert use(world, "update_profile", {"vaccinated": "no"}, **ctx).is_error


def test_saving_rescores_and_reports_a_new_hot_lead(world):
    hot = {
        "phone": "01712345678",
        "intake": "2027-01",
        "english_test": "ielts",
        "english_score": "6.5",
        "target_countries": ["UK"],
    }
    first = use(world, "update_profile", hot)
    assert first.effects == ("profile_updated", "became_hot")
    assert world.contact_row()[5] == "hot"
    again = use(world, "update_profile", {"subject": "CSE"})
    assert again.effects == ("profile_updated",)  # still hot: no second alert


def test_flags_are_stored(world):
    use(world, "update_profile", {"study_gap_years": 6, "previous_refusal": "UK 2024"})
    assert world.contact_row()[6] == ["refusal", "long_gap"]


def test_missing_contact(world):
    result = use(world, "update_profile", {"subject": "x"}, contact_id=999_999)
    assert result.content == {"error": "contact not found"}


# ---------- list_slots ----------


def test_list_slots(world):
    result = use(world, "list_slots", {})
    assert result.content == {
        "slots": [
            {
                "slot_id": f"{world.branch}@2026-10-05T04:00Z",
                "branch": "Banani",
                "start": "Mon 05 Oct 10:00",
                "seats_left": 1,
            },
            {
                "slot_id": f"{world.branch}@2026-10-05T05:00Z",
                "branch": "Banani",
                "start": "Mon 05 Oct 11:00",
                "seats_left": 1,
            },
            {
                "slot_id": f"{world.branch}@2026-10-12T04:00Z",
                "branch": "Banani",
                "start": "Mon 12 Oct 10:00",
                "seats_left": 1,
            },
            {
                "slot_id": f"{world.branch}@2026-10-12T05:00Z",
                "branch": "Banani",
                "start": "Mon 12 Oct 11:00",
                "seats_left": 1,
            },
        ],
        "timezone": "Asia/Dhaka",
    }


def test_list_slots_by_branch_name_and_date(world):
    result = use(world, "list_slots", {"branch": " banani ", "from_date": "2026-10-10"})
    assert [s["start"] for s in result.content["slots"]] == [
        "Mon 12 Oct 10:00",
        "Mon 12 Oct 11:00",
        "Mon 19 Oct 10:00",  # the window runs 14 days from the start date
        "Mon 19 Oct 11:00",
    ]


@pytest.mark.parametrize(
    "args, message",
    [
        ({"branch": "Gulshan"}, "unknown branch; choose one of: Banani"),
        ({"branch": 5}, "unknown branch"),
        ({"from_date": "next week"}, "from_date must be YYYY-MM-DD"),
        ({"from_date": 20261010}, "from_date must be YYYY-MM-DD"),
        ({"mode": "online"}, "unknown field(s): mode"),
    ],
)
def test_list_slots_errors(world, args, message):
    assert message in use(world, "list_slots", args).content["error"]


def test_no_open_slots_is_said_plainly(world):
    result = use(world, "list_slots", {}, tenant_id=world.other_tenant)
    assert result.content == {
        "slots": [],
        "timezone": "Asia/Dhaka",
        "note": "no open times in the next two weeks",
    }


# ---------- book_appointment ----------


def slot(world, when=MONDAY_10):
    return f"{world.branch}@{when.astimezone(UTC):%Y-%m-%dT%H:%MZ}"


def book(world, **args):
    return use(
        world,
        "book_appointment",
        {"slot_id": slot(world), "name": "Rahim", "phone": "01712345678"} | args,
    )


def test_booking(world):
    result = book(world)
    assert not result.is_error
    assert result.content == {
        "booked": True,
        "booking_id": result.content["booking_id"],
        "branch": "Banani",
        "start": "Mon 05 Oct 10:00",
    }
    assert result.effects == ("profile_updated", "booked")
    name, phone, *_, status = world.contact_row()
    assert (name, phone, status) == ("Rahim", "+8801712345678", "booked")


def test_booking_twice_is_the_same_booking(world):
    assert book(world).content["booking_id"] == book(world).content["booking_id"]


def test_full_slot_offers_alternatives_and_keeps_the_details(world):
    other = World.__new__(World)
    other.conn = world.conn
    rival, _ = other._person(world.tenant, "u2")
    use(
        world,
        "book_appointment",
        {"slot_id": slot(world), "name": "Karim", "phone": "01812345678"},
        contact_id=rival,
    )
    result = book(world)
    assert result.is_error
    assert result.content["error"] == "not booked: that slot is full"
    assert [a["start"] for a in result.content["alternatives"]] == [
        "Mon 05 Oct 11:00",
        "Mon 12 Oct 10:00",
        "Mon 12 Oct 11:00",
    ]
    assert world.contact_row()[:2] == ("Rahim", "+8801712345678")  # saved anyway


def test_a_time_that_isnt_open(world):
    result = book(world, slot_id=slot(world, MONDAY_10 - datetime.timedelta(days=7)))
    assert result.content["error"] == "not booked: that time isn't an open slot"
    assert len(result.content["alternatives"]) == 3


def test_another_companys_branch(world):
    result = book(world, slot_id=f"{world.other_branch}@2026-10-05T04:00Z")
    assert result.content["error"] == "not booked: branch not found"
    assert result.content["alternatives"][0]["branch"] == "Banani"  # ours, not theirs


@pytest.mark.parametrize("slot_id", ["tomorrow", "x@2026-10-05T04:00Z", "3@2026-10-05", 5])
def test_slot_id_must_come_from_list_slots(world, slot_id):
    result = book(world, slot_id=slot_id)
    assert result.content == {"error": "slot_id must be one returned by list_slots"}


def test_booking_needs_valid_name_and_phone(world):
    result = book(world, phone="123", name="42")
    assert result.content["error"].startswith("not booked; fix: name: not a name; phone:")
    assert world.contact_row()[0] is None


def test_booking_needs_every_field(world):
    result = use(world, "book_appointment", {"slot_id": slot(world)})
    assert result.content == {"error": "missing: name, phone"}


def test_booking_doesnt_move_a_later_stage_back(world):
    world.conn.execute("UPDATE contacts SET status = 'in_progress' WHERE id = %s", (world.contact,))
    book(world)
    assert world.contact_row()[7] == "in_progress"


# ---------- register_event ----------


def event(world, days=3, capacity=None, tenant=None):
    return one(
        world.conn,
        "INSERT INTO events (tenant_id, title, starts_at, capacity)"
        " VALUES (%s, 'UK Education Fair', %s, %s) RETURNING id",
        (tenant or world.tenant, NOW + datetime.timedelta(days=days), capacity),
    )


def register(world, event_id, **ctx):
    args = {"event_id": event_id, "name": "Rahim", "phone": "01712345678"}
    return use(world, "register_event", args, **ctx)


def test_register_for_an_event(world):
    result = register(world, event(world))
    assert result.content == {
        "registered": True,
        "event": "UK Education Fair",
        "starts": "Wed 07 Oct 12:00",
    }
    assert result.effects == ("profile_updated", "registered")
    assert world.contact_row()[0] == "Rahim"


def test_registering_twice_is_fine(world):
    e = event(world)
    register(world, e)
    again = register(world, e)
    assert again.content["registered"] is True and "registered" not in again.effects
    assert one(world.conn, "SELECT count(*) FROM event_registrations") == 1


def test_cancelled_registration_can_register_again(world):
    e = event(world)
    register(world, e)
    world.conn.execute("UPDATE event_registrations SET status = 'cancelled'")
    assert "registered" in register(world, e).effects
    assert one(world.conn, "SELECT status FROM event_registrations") == "registered"


def test_full_event(world):
    e = event(world, capacity=1)
    other = World.__new__(World)
    other.conn = world.conn
    rival, _ = other._person(world.tenant, "u2")
    register(world, e, contact_id=rival)
    result = register(world, e)
    assert result.content == {"error": "that event is full"}


@pytest.mark.parametrize("which", ["past", "other_company", "missing"])
def test_unavailable_events_list_the_upcoming_ones(world, which):
    upcoming = event(world, days=5)
    target = {
        "past": lambda: event(world, days=-1),
        "other_company": lambda: event(world, tenant=world.other_tenant),
        "missing": lambda: 999_999,
    }[which]()
    result = register(world, target)
    assert result.content["error"] == "no upcoming event with that id"
    assert [e["event_id"] for e in result.content["upcoming"]] == [upcoming]


@pytest.mark.parametrize("event_id", ["1", True, 1.5])
def test_event_id_must_be_a_number(world, event_id):
    assert "event_id must be a number" in register(world, event_id).content["error"]


# ---------- log_unanswered, off_topic ----------


def test_log_unanswered_records_and_counts(world):
    result = use(world, "log_unanswered", {"question": "  Is  Hungary  cheap? "})
    assert result == ToolResult({"logged": True}, effects=("unanswered",))
    use(world, "log_unanswered", {"question": "Visa for Poland?"})
    assert world.events("unanswered") == [
        ({"question": "Is Hungary cheap?"},),
        ({"question": "Visa for Poland?"},),
    ]
    assert (
        one(
            world.conn,
            "SELECT unanswered_streak FROM conversations WHERE id = %s",
            (world.conversation,),
        )
        == 2
    )


def test_log_unanswered_needs_a_question(world):
    assert use(world, "log_unanswered", {"question": " "}).content == {
        "error": "must be non-empty text"
    }


def test_off_topic_is_recorded(world):
    assert use(world, "off_topic", {}).effects == ("off_topic",)
    assert world.events("off_topic") == [({},)]
    assert use(world, "off_topic", {"why": "code"}).content == {"error": "unknown field(s): why"}


# ---------- request_handoff ----------


def conversation_state(world):
    return world.conn.execute(
        "SELECT state, paused_until FROM conversations WHERE id = %s", (world.conversation,)
    ).fetchone()


def test_handoff(world):
    result = use(world, "request_handoff", {"reason": "visa_case", "summary": "UK refusal 2024"})
    assert result == ToolResult({"handoff": True}, effects=("handoff",))
    state, paused_until = conversation_state(world)
    assert state == "human"
    assert paused_until == NOW + datetime.timedelta(hours=24)
    assert world.events("handoff") == [({"reason": "visa_case", "summary": "UK refusal 2024"},)]


def test_handoff_twice_is_one_handoff(world):
    args = {"reason": "asked_for_human", "summary": "wants a call"}
    use(world, "request_handoff", args)
    assert use(world, "request_handoff", args) == ToolResult({"handoff": "already with a person"})
    assert len(world.events("handoff")) == 1


def test_handoff_pause_follows_the_company_setting(world):
    use(world, "request_handoff", {"reason": "complaint", "summary": "x"}, pause_hours=2)
    assert conversation_state(world)[1] == NOW + datetime.timedelta(hours=2)


@pytest.mark.parametrize(
    "args, message",
    [
        ({"reason": "bored", "summary": "x"}, "reason must be one of: asked_for_human"),
        ({"reason": "visa_case", "summary": "  "}, "must be non-empty text"),
        ({"reason": "complaint"}, "missing: summary"),
    ],
)
def test_handoff_errors(world, args, message):
    assert message in use(world, "request_handoff", args).content["error"]
    assert conversation_state(world)[0] == "bot"


def test_pack_reason_only_in_its_own_industry(world):
    result = use(world, "request_handoff", {"reason": "visa_case", "summary": "x"}, pack=PETS)
    assert result.is_error


def test_handoff_for_another_companys_conversation(world):
    result = use(
        world,
        "request_handoff",
        {"reason": "complaint", "summary": "x"},
        conversation_id=world.other_conversation,
    )
    assert result.content == {"error": "conversation not found"}


# ---------- result blocks ----------


def test_result_block_is_compact_json():
    call = ToolCall("toolu_1", "list_slots", {})
    ok = result_block(call, ToolResult({"slots": [], "timezone": "Asia/Dhaka"}))
    assert ok == {
        "type": "tool_result",
        "tool_use_id": "toolu_1",
        "content": '{"slots":[],"timezone":"Asia/Dhaka"}',
        "is_error": False,
    }
    bad = result_block(call, ToolResult({"error": "x"}, is_error=True))
    assert bad["is_error"] is True
