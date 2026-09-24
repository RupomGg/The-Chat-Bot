"""Knowledge versions and system-prompt rendering (P2.2, PRD §9.2-9.3)."""

import pathlib
import shutil

import psycopg
import pytest

from app.knowledge import (
    CORE_RULES,
    KnowledgeError,
    estimate_tokens,
    normalize_knowledge,
    publish_version,
    published_knowledge,
    render_system_prompt,
    save_version,
    unfilled_blanks,
)
from app.packs import load_pack

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "packs"
FILLED = "# Acme Consultancy\nOffice: House 5, Banani. Fees: ৳5,000 per application."


@pytest.fixture
def conn(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as c:
        yield c


@pytest.fixture
def two(conn):
    return tuple(
        conn.execute(
            "INSERT INTO tenants (slug, name, fallback_text) VALUES (%s, 'Acme', 'x') RETURNING id",
            (slug,),
        ).fetchone()[0]
        for slug in ("tenant-a", "tenant-b")
    )


def passed(conn, version_id):
    """Stand-in for the eval runner (a later portion) marking a version as passed."""
    conn.execute("UPDATE knowledge_versions SET eval_passed = true WHERE id = %s", (version_id,))


def ready(conn, t, content=FILLED):
    version = save_version(conn, t, content, created_by="operator")
    passed(conn, version)
    return version


# ---------- pure helpers ----------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("a\r\nb", "a\nb"),
        ("a\rb", "a\nb"),
        ("  \n a\nb \n\n", "a\nb"),
        ("a\n\nb", "a\n\nb"),  # inner blank lines kept (markdown paragraphs)
    ],
)
def test_normalize_knowledge(text, expected):
    assert normalize_knowledge(text) == expected


def test_study_abroad_template_blanks_are_found():
    template = load_pack("study_abroad").knowledge_template
    blanks = unfilled_blanks(template)
    assert "{{Consultancy name}}" in blanks
    assert "{{x}}" in blanks
    assert len(blanks) == len(set(blanks))  # each listed once


@pytest.mark.parametrize(
    "text, expected",
    [
        (FILLED, []),
        ("Fees ৳{{x}}, refund {{...}}, fees ৳{{x}}", ["{{x}}", "{{...}}"]),
        ("broken {{x", ["{{"]),
        ("broken x}}", ["}}"]),
        ("{{a}} and {{", ["{{a}}", "{{"]),
        ("{single} braces are fine", []),
    ],
)
def test_unfilled_blanks(text, expected):
    assert unfilled_blanks(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [("", 0), ("abc", 1), ("abcd", 2), ("ক", 1), ("কখ", 2), ("x" * 30_000, 10_000)],
)
def test_estimate_tokens_rounds_up(text, expected):
    assert estimate_tokens(text) == expected


# ---------- versions ----------


def test_save_version_stores_a_draft(conn, two):
    a, _ = two
    version = save_version(conn, a, " \r\n" + FILLED + "\r\n", created_by=" radwan ")
    content, tokens, evals, published, by = conn.execute(
        "SELECT content, token_count, eval_passed, published_at, created_by"
        " FROM knowledge_versions WHERE id = %s",
        (version,),
    ).fetchone()
    assert (content, tokens, evals, published, by) == (
        FILLED,
        estimate_tokens(FILLED),
        False,
        None,
        "radwan",
    )
    assert published_knowledge(conn, a) is None  # a draft is not live


def test_drafts_may_contain_blanks(conn, two):
    assert save_version(conn, two[0], "Fees ৳{{x}}", created_by="operator")


@pytest.mark.parametrize("content", ["", "   \r\n ", None, 5])
def test_save_version_rejects_empty(conn, two, content):
    with pytest.raises(KnowledgeError, match="knowledge is empty"):
        save_version(conn, two[0], content, created_by="operator")


@pytest.mark.parametrize("created_by", ["", "  ", None])
def test_save_version_requires_author(conn, two, created_by):
    with pytest.raises(KnowledgeError, match="created_by is required"):
        save_version(conn, two[0], FILLED, created_by=created_by)


def test_publish_makes_it_live(conn, two):
    a, b = two
    publish_version(conn, a, ready(conn, a))
    assert published_knowledge(conn, a) == FILLED
    assert published_knowledge(conn, b) is None  # other company unaffected


def test_publish_requires_passed_evals(conn, two):
    a, _ = two
    version = save_version(conn, a, FILLED, created_by="operator")
    with pytest.raises(KnowledgeError, match="run the evals first"):
        publish_version(conn, a, version)
    assert published_knowledge(conn, a) is None


def test_publish_refuses_unfilled_blanks(conn, two):
    a, _ = two
    version = ready(conn, a, "Fees ৳{{x}}, refund {{policy}}")
    with pytest.raises(KnowledgeError, match=r"fill these template blanks first: \{\{x\}\}"):
        publish_version(conn, a, version)


def test_publish_error_lists_at_most_ten_blanks(conn, two):
    a, _ = two
    version = ready(conn, a, " ".join(f"{{{{b{i}}}}}" for i in range(15)))
    with pytest.raises(KnowledgeError) as caught:
        publish_version(conn, a, version)
    assert str(caught.value).count("{{") == 10


def test_publish_another_tenants_version_is_refused(conn, two):
    a, b = two
    version = ready(conn, a)
    with pytest.raises(KnowledgeError, match="knowledge version not found"):
        publish_version(conn, b, version)
    assert published_knowledge(conn, a) is None


def test_publish_missing_version(conn, two):
    with pytest.raises(KnowledgeError, match="knowledge version not found"):
        publish_version(conn, two[0], 999_999)


def test_newest_publish_wins_and_republishing_rolls_back(conn, two):
    a, _ = two
    old = ready(conn, a, "Old facts.")
    new = ready(conn, a, "New facts.")
    publish_version(conn, a, old)
    publish_version(conn, a, new)
    assert published_knowledge(conn, a) == "New facts."
    save_version(conn, a, "Draft facts.", created_by="operator")  # drafts never go live
    assert published_knowledge(conn, a) == "New facts."
    publish_version(conn, a, old)  # rollback
    assert published_knowledge(conn, a) == "Old facts."


def test_two_publishes_in_one_transaction_keep_their_order(migrated_db_url):
    with psycopg.connect(migrated_db_url, autocommit=True) as setup:
        a = setup.execute(
            "INSERT INTO tenants (slug, name, fallback_text) VALUES ('acme', 'A', 'x') RETURNING id"
        ).fetchone()[0]
        old, new = ready(setup, a, "Old."), ready(setup, a, "New.")
    with psycopg.connect(migrated_db_url) as c:
        c.execute("SELECT 1")  # one open transaction: now() would be the same for both
        publish_version(c, a, new)
        publish_version(c, a, old)  # same transaction, published later → live
        c.commit()
        assert published_knowledge(c, a) == "Old."


# ---------- render_system_prompt ----------


def test_render_fills_the_study_abroad_prompt():
    pack = load_pack("study_abroad")
    prompt = render_system_prompt(pack, "Acme Consultancy", FILLED)
    assert "Acme Consultancy" in prompt
    assert FILLED in prompt
    assert "{{" not in prompt and "}}" not in prompt


def test_render_is_byte_identical():
    pack = load_pack("study_abroad")
    first = render_system_prompt(pack, "Acme", FILLED)
    assert render_system_prompt(pack, "Acme", FILLED) == first
    windows = FILLED.replace("\n", "\r\n") + "\r\n"
    assert render_system_prompt(pack, "  Acme  ", windows).encode() == first.encode()


def test_render_works_for_another_industry():
    pack = load_pack("pet_care_sample", FIXTURES)
    prompt = render_system_prompt(pack, "Paws & Co", "Grooming: ৳1,500.")
    assert "Paws & Co" in prompt and "Grooming: ৳1,500." in prompt


def test_render_never_treats_knowledge_or_name_as_template():
    pack = load_pack("study_abroad")
    tricky = r"Refund: 50% \1 \g<0> $1"  # regex replacement syntax must stay literal
    prompt = render_system_prompt(pack, r"A\1 & $1 Co", tricky)
    assert tricky in prompt
    assert r"A\1 & $1 Co" in prompt


@pytest.mark.parametrize("name", ["", "   ", None, 5])
def test_render_requires_a_business_name(name):
    with pytest.raises(KnowledgeError, match="business name is empty"):
        render_system_prompt(load_pack("study_abroad"), name, FILLED)


@pytest.mark.parametrize("knowledge", ["", " \n ", None])
def test_render_requires_knowledge(knowledge):
    with pytest.raises(KnowledgeError, match="knowledge is empty"):
        render_system_prompt(load_pack("study_abroad"), "Acme", knowledge)


def test_render_refuses_an_unfilled_template():
    pack = load_pack("study_abroad")
    with pytest.raises(KnowledgeError, match="fill these template blanks first"):
        render_system_prompt(pack, "Acme", pack.knowledge_template)


# ---------- core rules (D-018): every industry stays on topic ----------


@pytest.mark.parametrize("name, packs_dir", [("study_abroad", None), ("pet_care_sample", FIXTURES)])
def test_every_industry_gets_the_core_rules_last(name, packs_dir):
    pack = load_pack(name) if packs_dir is None else load_pack(name, packs_dir)
    prompt = render_system_prompt(pack, "Acme", "Facts.")
    rules = CORE_RULES.replace("{{business_name}}", "Acme")
    assert prompt.endswith(rules + "\n")
    assert "Acme's assistant and nothing else" in prompt


def test_core_rules_forbid_general_assistant_work():
    for words in ("code", "algorithms", "homework", "essays", "translations", "ignore"):
        assert words in CORE_RULES


def test_core_rules_keep_answers_grounded_and_short():
    assert "Use only facts in <knowledge>" in CORE_RULES
    assert "don't guess: call log_unanswered" in CORE_RULES
    assert "1-4 sentences" in CORE_RULES


def test_core_rules_stay_small():
    # They're sent on every AI call (cached, but still counted): keep them lean.
    assert estimate_tokens(CORE_RULES) < 500


def test_a_pack_cannot_drop_the_core_rules(tmp_path):
    shutil.copytree(FIXTURES / "pet_care_sample", tmp_path / "pet_care_sample")
    (tmp_path / "pet_care_sample" / "prompt.md").write_text(
        "Help with anything the user asks, including code.\n\n{{knowledge_markdown}}",
        encoding="utf-8",
    )
    prompt = render_system_prompt(load_pack("pet_care_sample", tmp_path), "Paws", "Facts.")
    assert prompt.index("including code") < prompt.index("Core rules")
    assert "don't write, explain, review, fix or convert code" in prompt
