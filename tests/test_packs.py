"""Industry pack loader (P2.0, D-012): a broken pack must never reach a tenant."""

import pathlib
import shutil

import pytest

from app import packs
from app.packs import GENERIC_STAGES, Pack, PackError, load_pack

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "packs"
SAMPLE = "pet_care_sample"


@pytest.fixture
def packs_dir(tmp_path):
    shutil.copytree(FIXTURES / SAMPLE, tmp_path / SAMPLE)
    return tmp_path


def edit(packs_dir, old, new, file="pack.toml"):
    path = packs_dir / SAMPLE / file
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"test setup: {old!r} not found exactly once"
    path.write_text(text.replace(old, new), encoding="utf-8")


def error(packs_dir):
    with pytest.raises(PackError) as exc:
        load_pack(SAMPLE, packs_dir)
    return str(exc.value)


# ---------- valid packs ----------


def test_real_study_abroad_pack_loads():
    pack = load_pack("study_abroad")
    assert isinstance(pack, Pack)
    assert pack.name == "study_abroad"
    assert set(pack.stages) == set(GENERIC_STAGES)
    names = [f.name for f in pack.fields]
    for expected in ("current_level", "english_test", "target_countries", "intake", "funding"):
        assert expected in names
    assert "{{knowledge_markdown}}" in pack.prompt
    assert "{{business_name}}" in pack.prompt
    assert pack.tenant_settings == {"served_countries": "list"}
    assert pack.scoring.hot and pack.scoring.warm
    assert {f.name for f in pack.scoring.flags} == {"refusal", "long_gap", "scholarship_only"}


def test_study_abroad_labels_in_english_and_bangla():
    pack = load_pack("study_abroad")
    for stage in GENERIC_STAGES:
        assert pack.stages[stage]["en"]
        assert pack.stages[stage]["bn"]


def test_second_industry_loads(packs_dir):
    pack = load_pack(SAMPLE, packs_dir)
    assert pack.display_name == "Pet care centre (sample)"
    assert pack.stages["booked"] == {"en": "Appointment booked"}
    assert pack.stages["new"]["bn"] == "নতুন"  # Bangla text survives loading
    species = next(f for f in pack.fields if f.name == "species")
    assert species.type == "choice" and species.choices == ("dog", "cat", "bird", "other")
    assert species.label == {"en": "Species", "bn": "প্রাণী"}


def test_loading_twice_gives_equal_results(packs_dir):
    assert load_pack(SAMPLE, packs_dir) == load_pack(SAMPLE, packs_dir)


def test_pack_is_immutable(packs_dir):
    pack = load_pack(SAMPLE, packs_dir)
    with pytest.raises(AttributeError):
        pack.name = "other"


def test_nested_any_condition_parsed(packs_dir):
    pack = load_pack(SAMPLE, packs_dir)
    any_rule = next(c for c in pack.scoring.hot if c.any)
    assert [c.op for c in any_rule.any] == ["in", "gte"]


# ---------- names and files ----------


@pytest.mark.parametrize(
    "name", ["../secrets", "..", "study_abroad/..", "Pet", "pet-care", "p", "", "a" * 41, "1pets"]
)
def test_bad_pack_names_rejected_before_touching_disk(name, tmp_path):
    with pytest.raises(PackError, match="invalid pack name"):
        load_pack(name, tmp_path)


def test_missing_pack_folder(tmp_path):
    with pytest.raises(PackError, match="pack 'no_such_pack' not found"):
        load_pack("no_such_pack", tmp_path)


@pytest.mark.parametrize("missing", ["pack.toml", "prompt.md", "knowledge_template.md"])
def test_missing_file_named(packs_dir, missing):
    (packs_dir / SAMPLE / missing).unlink()
    assert f"{SAMPLE}/{missing}: missing" in error(packs_dir)


def test_name_must_match_folder(packs_dir):
    edit(packs_dir, 'name = "pet_care_sample"', 'name = "pet_care"')
    assert "name 'pet_care' doesn't match its folder 'pet_care_sample'" in error(packs_dir)


def test_invalid_toml_is_reported_with_file(packs_dir):
    edit(packs_dir, "version = 1", "version = = 1")
    assert "pack.toml: not valid TOML" in error(packs_dir)


def test_non_utf8_file_reported(packs_dir):
    (packs_dir / SAMPLE / "prompt.md").write_bytes(b"\xff\xfe {{knowledge_markdown}}")
    assert "prompt.md: not valid UTF-8" in error(packs_dir)


# ---------- top level ----------


def test_unknown_top_level_key(packs_dir):
    edit(packs_dir, "version = 1", "version = 1\ncolour = 'blue'")
    assert "unknown key 'colour'" in error(packs_dir)


@pytest.mark.parametrize(
    "old, new, message",
    [
        ('display_name = "Pet care centre (sample)"\n', "", "missing key 'display_name'"),
        ('display_name = "Pet care centre (sample)"', 'display_name = "  "', "display_name"),
        ("version = 1", "version = 0", "version"),
        ("version = 1", 'version = "1"', "version"),
    ],
)
def test_bad_top_level_values(packs_dir, old, new, message):
    edit(packs_dir, old, new)
    assert message in error(packs_dir)


# ---------- stages ----------


def test_stage_missing(packs_dir):
    edit(packs_dir, 'qualified = { en = "Qualified" }\n', "")
    assert "stages: missing 'qualified'" in error(packs_dir)


def test_stage_unknown(packs_dir):
    edit(packs_dir, 'lost = { en = "Lost" }', 'lost = { en = "Lost" }\nparked = { en = "Parked" }')
    assert "stages: unknown 'parked'" in error(packs_dir)


def test_stage_needs_english_label(packs_dir):
    edit(packs_dir, 'won = { en = "Visited" }', 'won = { bn = "এসেছে" }')
    assert "stages.won: needs an 'en' label" in error(packs_dir)


def test_stage_label_must_be_text(packs_dir):
    edit(packs_dir, 'won = { en = "Visited" }', 'won = { en = "" }')
    assert "stages.won" in error(packs_dir)


def test_stage_label_language_code_checked(packs_dir):
    edit(packs_dir, 'won = { en = "Visited" }', 'won = { en = "Visited", Bangla = "x" }')
    assert "stages.won: bad language code 'Bangla'" in error(packs_dir)


# ---------- fields ----------


def test_field_unknown_type(packs_dir):
    edit(packs_dir, 'type = "bool"', 'type = "boolean"')
    assert "fields.vaccinated: unknown type 'boolean'" in error(packs_dir)


def test_field_duplicate_name(packs_dir):
    edit(packs_dir, 'name = "pet_name"', 'name = "species"')
    assert "fields: duplicate 'species'" in error(packs_dir)


@pytest.mark.parametrize("builtin", ["phone", "name", "adult"])
def test_field_cannot_shadow_builtin(packs_dir, builtin):
    edit(packs_dir, 'name = "pet_name"', f'name = "{builtin}"')
    assert f"fields.{builtin}: '{builtin}' is built in" in error(packs_dir)


@pytest.mark.parametrize("bad", ["Pet", "pet-name", "1pet", ""])
def test_field_name_format(packs_dir, bad):
    edit(packs_dir, 'name = "pet_name"', f'name = "{bad}"')
    assert "invalid field name" in error(packs_dir)


def test_choice_field_needs_choices(packs_dir):
    edit(packs_dir, 'choices = ["dog", "cat", "bird", "other"]\n', "")
    assert "fields.species: a choice field needs 'choices'" in error(packs_dir)


def test_choices_must_be_unique_and_non_empty(packs_dir):
    edit(packs_dir, '["dog", "cat", "bird", "other"]', '["dog", "dog"]')
    assert "fields.species: choices must be unique" in error(packs_dir)
    edit(packs_dir, '["dog", "dog"]', "[]")
    assert "fields.species: a choice field needs 'choices'" in error(packs_dir)


def test_choices_only_on_choice_fields(packs_dir):
    edit(packs_dir, 'type = "text"', 'type = "text"\nchoices = ["a"]')
    assert "fields.pet_name: only choice fields have 'choices'" in error(packs_dir)


def test_field_priority_checked(packs_dir):
    edit(packs_dir, 'priority = "low"', 'priority = "urgent"')
    assert "fields.pet_age_years: priority must be high, medium or low" in error(packs_dir)


def test_field_unknown_key_catches_typos(packs_dir):
    edit(packs_dir, 'priority = "low"', 'priorty = "low"')
    assert "fields.pet_age_years: unknown key 'priorty'" in error(packs_dir)


def test_field_needs_english_label(packs_dir):
    edit(packs_dir, 'label = { en = "Pet\'s name" }', 'label = { bn = "নাম" }')
    assert "fields.pet_name.label: needs an 'en' label" in error(packs_dir)


def test_at_least_one_field(packs_dir):
    path = packs_dir / SAMPLE / "pack.toml"
    text = path.read_text(encoding="utf-8")
    start, end = text.index("[[fields]]"), text.index("[scoring]")
    path.write_text(
        text[:start] + text[end:].replace("[scoring]", "[scoring]", 1), encoding="utf-8"
    )
    # scoring now refers to fields that no longer exist, so check the first problem reported
    assert "fields: at least one field is required" in error(packs_dir)


# ---------- scoring ----------


def test_rule_on_unknown_field(packs_dir):
    edit(
        packs_dir,
        '{ field = "phone", op = "present" },\n]',
        '{ field = "phone", op = "present" },\n    { field = "colour", op = "present" },\n]',
    )
    assert "scoring.warm[1]: unknown field 'colour'" in error(packs_dir)


def test_rule_unknown_op(packs_dir):
    edit(
        packs_dir,
        '{ field = "phone", op = "present" },\n]',
        '{ field = "phone", op = "exists" },\n]',
    )
    assert "scoring.warm[0]: unknown op 'exists'" in error(packs_dir)


def test_choice_values_must_be_real_choices(packs_dir):
    edit(packs_dir, 'values = ["dog", "cat"]', 'values = ["Dog", "cat"]')
    assert "scoring.hot[2].any[0]: 'Dog' is not a choice of species" in error(packs_dir)


@pytest.mark.parametrize(
    "old, new, message",
    [
        (
            'op = "gte", value = 10 },\n    ] },',
            'op = "gte", value = "10" },\n    ] },',
            "needs a whole number",
        ),
        (
            'op = "within_months", months = 1',
            'op = "within_months", months = 0',
            "months must be 1-120",
        ),
        (
            'op = "within_months", months = 1',
            'op = "within_months", months = 121',
            "months must be 1-120",
        ),
        ('op = "within_months", months = 1', 'op = "within_months"', "months must be 1-120"),
        (
            '{ field = "visit_month", op = "within_months", months = 1 }',
            '{ field = "species", op = "within_months", months = 1 }',
            "'within_months' doesn't work on a choice field",
        ),
        (
            '{ field = "visit_month", op = "within_months", months = 1 }',
            '{ field = "species", op = "gte", value = 1 }',
            "'gte' doesn't work on a choice field",
        ),
        (
            '{ field = "visit_month", op = "within_months", months = 1 }',
            '{ field = "phone", op = "eq", value = "x" }',
            "'eq' doesn't work on phone",
        ),
        (
            '{ field = "visit_month", op = "within_months", months = 1 }',
            '{ field = "species", op = "in", values = [] }',
            "needs a non-empty 'values' list",
        ),
        (
            '{ field = "visit_month", op = "within_months", months = 1 }',
            '{ field = "species", op = "eq" }',
            "needs a 'value'",
        ),
        (
            '{ field = "visit_month", op = "within_months", months = 1 }',
            '{ field = "vaccinated", op = "eq", value = "no" }',
            "needs true or false",
        ),
        (
            '{ field = "visit_month", op = "within_months", months = 1 }',
            '{ field = "species", op = "eq", value = "fish" }',
            "'fish' is not a choice of species",
        ),
        (
            '{ field = "visit_month", op = "within_months", months = 1 }',
            '{ field = "visit_month", op = "present", months = 1 }',
            "unexpected key 'months'",
        ),
    ],
)
def test_bad_rule_arguments(packs_dir, old, new, message):
    edit(packs_dir, old, new)
    assert message in error(packs_dir)


def test_overlaps_setting_must_be_declared(packs_dir):
    edit(packs_dir, 'setting = "services_offered"', 'setting = "services"')
    assert "scoring.hot[1]: setting 'services' is not declared in [tenant_settings]" in error(
        packs_dir
    )


def test_overlaps_setting_needs_list_field(packs_dir):
    edit(
        packs_dir,
        '{ field = "needs", op = "overlaps_setting"',
        '{ field = "species", op = "overlaps_setting"',
    )
    assert "'overlaps_setting' doesn't work on a choice field" in error(packs_dir)


def test_any_must_be_a_non_empty_list(packs_dir):
    path = packs_dir / SAMPLE / "pack.toml"
    text = path.read_text(encoding="utf-8")
    start = text.index("    { any = [")
    end = text.index("    ] },", start) + len("    ] },")
    path.write_text(text[:start] + "    { any = [] }," + text[end:], encoding="utf-8")
    assert "scoring.hot[2]: 'any' needs at least one condition" in error(packs_dir)


def test_rule_cannot_mix_any_and_field(packs_dir):
    edit(packs_dir, "{ any = [", '{ field = "phone", any = [')
    assert "scoring.hot[2]: use either 'any' or 'field', not both" in error(packs_dir)


def test_hot_and_warm_required(packs_dir):
    edit(packs_dir, 'warm = [\n    { field = "phone", op = "present" },\n]\n', "")
    assert "scoring: missing 'warm'" in error(packs_dir)


def test_flag_names_unique_and_formatted(packs_dir):
    edit(packs_dir, 'name = "senior_pet"', 'name = "not_vaccinated"')
    assert "scoring.flags: duplicate flag 'not_vaccinated'" in error(packs_dir)
    edit(
        packs_dir,
        'name = "not_vaccinated", when = [{ field = "pet_age_years"',
        'name = "Senior Pet", when = [{ field = "pet_age_years"',
    )
    assert "invalid flag name 'Senior Pet'" in error(packs_dir)


def test_flag_needs_conditions(packs_dir):
    edit(packs_dir, 'when = [{ field = "pet_age_years", op = "gte", value = 10 }]', "when = []")
    assert "scoring.flags[1]: 'when' needs at least one condition" in error(packs_dir)


def test_tenant_setting_type_checked(packs_dir):
    edit(packs_dir, 'services_offered = "list"', 'services_offered = "table"')
    assert "tenant_settings.services_offered: type must be list, text or int" in error(packs_dir)


# ---------- prompt ----------


def test_prompt_needs_knowledge_placeholder(packs_dir):
    edit(packs_dir, "{{knowledge_markdown}}", "(knowledge here)", file="prompt.md")
    assert "prompt.md: must contain {{knowledge_markdown}}" in error(packs_dir)


def test_prompt_unknown_placeholder(packs_dir):
    edit(packs_dir, "{{business_name}}", "{{consultancy_name}}", file="prompt.md")
    assert "prompt.md: unknown placeholder {{consultancy_name}}" in error(packs_dir)


@pytest.mark.parametrize("broken", ["{{business_name}", "{business_name}}", "{{ business_name }}"])
def test_prompt_malformed_placeholder(packs_dir, broken):
    edit(packs_dir, "{{business_name}}", broken, file="prompt.md")
    assert "prompt.md: malformed placeholder" in error(packs_dir)


def test_empty_prompt(packs_dir):
    (packs_dir / SAMPLE / "prompt.md").write_text("  \n", encoding="utf-8")
    assert "prompt.md: empty" in error(packs_dir)


def test_empty_knowledge_template(packs_dir):
    (packs_dir / SAMPLE / "knowledge_template.md").write_text("", encoding="utf-8")
    assert "knowledge_template.md: empty" in error(packs_dir)


def test_errors_list_every_problem(packs_dir):
    edit(packs_dir, 'priority = "low"', 'priority = "urgent"')
    edit(packs_dir, 'type = "bool"', 'type = "boolean"')
    message = error(packs_dir)
    assert "priority must be high, medium or low" in message
    assert "unknown type 'boolean'" in message


def test_default_packs_dir_is_the_repo_folder():
    assert packs.PACKS_DIR.name == "packs"
    assert (packs.PACKS_DIR / "study_abroad" / "pack.toml").is_file()


# ---------- wrong shapes (a hand-edited pack.toml can put anything anywhere) ----------


def cut(packs_dir, start, end):
    """Remove the text from `start` up to (not including) `end`."""
    path = packs_dir / SAMPLE / "pack.toml"
    text = path.read_text(encoding="utf-8")
    a = text.index(start)
    b = text.index(end, a)
    path.write_text(text[:a] + text[b:], encoding="utf-8")


def top(packs_dir, line):
    edit(packs_dir, "version = 1", f"version = 1\n{line}")


def test_stages_not_a_table(packs_dir):
    cut(packs_dir, "[stages]", "[[fields]]")
    top(packs_dir, 'stages = "all of them"')
    assert "stages: must be a table" in error(packs_dir)


def test_tenant_settings_not_a_table(packs_dir):
    cut(packs_dir, "[tenant_settings]", "[stages]")
    top(packs_dir, "tenant_settings = 3")
    assert "tenant_settings: must be a table" in error(packs_dir)


def test_fields_entry_not_a_table(packs_dir):
    cut(packs_dir, "[[fields]]", "[scoring]")
    top(packs_dir, 'fields = ["pet_name"]')
    assert "fields[0]: must be a table" in error(packs_dir)


def test_scoring_not_a_table(packs_dir):
    cut(packs_dir, "[scoring]", "flags = [")
    path = packs_dir / SAMPLE / "pack.toml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text[: text.index("flags = [")], encoding="utf-8")  # drop the rest too
    top(packs_dir, 'scoring = "hot if keen"')
    assert "scoring: must be a table" in error(packs_dir)


def test_label_not_a_table(packs_dir):
    edit(packs_dir, 'label = { en = "Pet\'s name" }', 'label = "Pet\'s name"')
    assert "fields.pet_name.label: must be a table of language = label" in error(packs_dir)


def test_setting_name_format(packs_dir):
    edit(packs_dir, 'services_offered = "list"', 'services_offered = "list"\nBad-Name = "text"')
    assert "tenant_settings: invalid setting name 'Bad-Name'" in error(packs_dir)


def test_rule_not_a_table(packs_dir):
    edit(packs_dir, 'warm = [\n    { field = "phone", op = "present" },\n]', 'warm = ["phone"]')
    assert "scoring.warm[0]: must be a table" in error(packs_dir)


@pytest.mark.parametrize("rules", ['"phone"', "[]"])
def test_rule_list_empty_or_not_a_list(packs_dir, rules):
    edit(packs_dir, 'warm = [\n    { field = "phone", op = "present" },\n]', f"warm = {rules}")
    assert "scoring.warm: needs at least one condition" in error(packs_dir)


def test_flag_not_a_table(packs_dir):
    edit(
        packs_dir,
        'flags = [\n    { name = "not_vaccinated"',
        'flags = [\n    "oops",\n    { name = "not_vaccinated"',
    )
    assert "scoring.flags[0]: must be a table" in error(packs_dir)


@pytest.mark.parametrize(
    "rule, message",
    [
        ('{ field = "species", op = "eq", value = 5 }', "needs non-empty text"),
        ('{ field = "pet_name", op = "eq", value = "" }', "needs non-empty text"),
        ('{ field = "pet_age_years", op = "eq", value = "ten" }', "needs a whole number 'value'"),
        ('{ field = "pet_age_years", op = "lte", value = true }', "needs a whole number 'value'"),
        (
            '{ field = "vaccinated", op = "in", values = [true] }',
            "'in' doesn't work on a bool field",
        ),
        ('{ field = "adult", op = "eq", value = true }', None),  # built-in bool: allowed
        ('{ field = "name", op = "present" }', None),  # built-in text: allowed
    ],
)
def test_rule_value_types(packs_dir, rule, message):
    edit(packs_dir, 'warm = [\n    { field = "phone", op = "present" },\n]', f"warm = [{rule}]")
    if message is None:
        assert load_pack(SAMPLE, packs_dir).scoring.warm
    else:
        assert message in error(packs_dir)


# ---------- terms and handoff reasons (D-020) ----------


def test_study_abroad_terms_and_handoff_reasons():
    pack = load_pack("study_abroad")
    assert pack.terms["appointment"]["en"] == "Counselling session"
    assert pack.terms["staff"]["en"] == "Counsellor"
    assert pack.handoff_reasons == ("visa_case", "fee_dispute")


def test_other_industry_uses_its_own_words():
    pack = load_pack(SAMPLE, FIXTURES)
    assert pack.terms == {"appointment": {"en": "Vet visit"}, "staff": {"en": "Vet"}}
    assert pack.handoff_reasons == ()  # optional


def test_terms_are_required(packs_dir):
    edit(packs_dir, '[terms]\nappointment = { en = "Vet visit" }\nstaff = { en = "Vet" }\n', "")
    assert "pack.toml: missing key 'terms'" in error(packs_dir)


def test_term_missing(packs_dir):
    edit(packs_dir, 'staff = { en = "Vet" }\n', "")
    assert "terms: missing 'staff'" in error(packs_dir)


def test_term_unknown(packs_dir):
    edit(packs_dir, 'staff = { en = "Vet" }', 'staff = { en = "Vet" }\nboss = { en = "Boss" }')
    assert "terms: unknown 'boss'" in error(packs_dir)


def test_terms_must_be_a_table(packs_dir):
    edit(
        packs_dir,
        '[terms]\nappointment = { en = "Vet visit" }\nstaff = { en = "Vet" }\n',
        "",
    )
    edit(packs_dir, "version = 1\n", 'version = 1\nterms = "vet"\n')
    assert "terms: must be a table" in error(packs_dir)


def test_term_needs_english_label(packs_dir):
    edit(packs_dir, 'staff = { en = "Vet" }', 'staff = { bn = "ডাক্তার" }')
    assert "terms.staff: needs an 'en' label" in error(packs_dir)


@pytest.mark.parametrize(
    "value, message",
    [
        ('"visa_case"', "handoff_reasons: must be a list of names"),
        ('["Visa Case"]', "handoff_reasons: invalid name 'Visa Case'"),
        ("[5]", "handoff_reasons: invalid name 5"),
        ('["complaint"]', "handoff_reasons: 'complaint' is already a core reason"),
        ('["vet_emergency", "vet_emergency"]', "handoff_reasons: 'vet_emergency' is listed twice"),
    ],
)
def test_handoff_reasons_checked(packs_dir, value, message):
    edit(packs_dir, "version = 1\n", f"version = 1\nhandoff_reasons = {value}\n")
    assert message in error(packs_dir)


def test_handoff_reasons_load(packs_dir):
    edit(packs_dir, "version = 1\n", 'version = 1\nhandoff_reasons = ["vet_emergency"]\n')
    assert load_pack(SAMPLE, packs_dir).handoff_reasons == ("vet_emergency",)
