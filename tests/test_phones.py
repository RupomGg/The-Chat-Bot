"""Phone normalization (P2.1): any messy input → E.164 or None, never an exception."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.phones import CALLING_CODES, normalize_phone

BD = "+8801712345678"

# ---------- Bangladesh: every common way of writing the same mobile ----------


@pytest.mark.parametrize(
    "raw",
    [
        "01712345678",
        "+8801712345678",
        "8801712345678",
        "008801712345678",
        "+880 1712-345678",
        "+880 1712 345 678",
        "017-1234-5678",
        "017.1234.5678",
        "(017) 1234 5678",
        "+880 (17) 12345678",
        "  01712345678  ",
        "\t01712345678\n",
        "০১৭১২৩৪৫৬৭৮",  # Bangla digits
        "+৮৮০১৭১২৩৪৫৬৭৮",
        "০1712345678",  # mixed Bangla and ASCII digits
        "０１７１２３４５６７８",  # full-width digits (some phone keyboards)
    ],
)
def test_bangladesh_formats_all_normalize_to_the_same_number(raw):
    assert normalize_phone(raw) == BD


@pytest.mark.parametrize("prefix", ["013", "014", "015", "016", "017", "018", "019"])
def test_every_bangladesh_mobile_operator_prefix(prefix):
    assert normalize_phone(prefix + "12345678") == "+880" + prefix[1:] + "12345678"


@pytest.mark.parametrize(
    "raw",
    [
        "01212345678",  # 012 isn't a mobile prefix
        "01012345678",
        "01112345678",
        "0171234567",  # 10 digits: one short
        "017123456789",  # 12 digits: one long
        "+88017123456789",
        "+880171234567",
        "02 9123456",  # Dhaka landline
        "+880 2 9123456",
        "+8802912345678",
        "1712345678",  # no leading 0 and no country code: ambiguous
    ],
)
def test_invalid_bangladesh_numbers_rejected(raw):
    assert normalize_phone(raw) is None


# ---------- junk never raises ----------


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "-- () ..",
        "+",
        "abc",
        "017-ABC-45678",
        "01712345678😀",
        "call me 01712345678",  # numbers inside sentences are NOT extracted
        "01712345678 or 01812345678",
        "++8801712345678",
        "880+1712345678",  # plus not at the start
        "+880/1712345678",
        "01712345678#",
        "017_1234_5678",
        "¹⁷¹²³⁴⁵⁶⁷⁸",  # superscripts look like digits but aren't
        "⁰¹⁷¹²³⁴⁵⁶⁷⁸",  # same, with the leading 0: only the digit check can reject it
        12345678901,  # not a string
        ["01712345678"],
        "0" * 10_000,  # absurdly long
    ],
)
def test_junk_returns_none(raw):
    assert normalize_phone(raw) is None


# ---------- other countries (tenant's country decides local numbers) ----------


@pytest.mark.parametrize(
    "raw, country, expected",
    [
        ("9812345678", "NP", "+9779812345678"),  # Nepal, no trunk 0
        ("+977 981-2345678", "NP", "+9779812345678"),
        ("०९८१२३४५६७८", "NP", "+9779812345678"),  # Devanagari digits, leading 0 dropped
        ("07911 123456", "GB", "+447911123456"),  # UK: trunk 0 dropped
        ("+44 7911 123456", "BD", "+447911123456"),  # international number, any tenant
        ("0300 1234567", "PK", "+923001234567"),
        ("98765 43210", "IN", "+919876543210"),
        ("(415) 555-2671", "US", "+14155552671"),
    ],
)
def test_other_countries(raw, country, expected):
    assert normalize_phone(raw, country) == expected


def test_bangladesh_rules_apply_to_plus880_whatever_the_tenant_country():
    assert normalize_phone("+880 1712 345678", "NP") == BD
    assert normalize_phone("+880 2 9123456", "NP") is None  # still a BD landline


def test_local_number_follows_the_tenants_country_not_bangladesh():
    # "01712345678" at a UK tenant is read as a UK number, never silently as Bangladeshi.
    assert normalize_phone("01712345678", "GB") == "+441712345678"
    assert normalize_phone("01712345678", "GB") != BD


@pytest.mark.parametrize(
    "raw",
    ["+1234", "+0123456789", "+1234567890123456", "001234"],  # too short, bad start, too long
)
def test_international_length_and_start_rules(raw):
    assert normalize_phone(raw, "GB") is None


def test_fifteen_digit_limit_for_countries_outside_the_table():
    # +85... isn't in our table, so only the general E.164 limit (15 digits) applies.
    assert normalize_phone("+859123456789012", "GB") == "+859123456789012"  # 15 digits
    assert normalize_phone("+8591234567890123", "GB") is None  # 16 digits


def test_input_over_64_characters_rejected_even_if_digits_are_valid():
    padded = "017" + "-" * 58 + "12345678"  # 69 characters, digits form a valid mobile
    assert len(padded) > 64
    assert normalize_phone(padded) is None
    assert normalize_phone("017" + "-" * 50 + "12345678") == BD  # 61 characters: fine


@pytest.mark.parametrize("country", ["ZZ", "bd", "", "BGD"])
def test_unknown_country_is_a_configuration_error(country):
    with pytest.raises(ValueError, match="unsupported country"):
        normalize_phone("01712345678", country)


def test_calling_codes_table_is_consistent():
    assert CALLING_CODES["BD"] == "880"
    for country, code in CALLING_CODES.items():
        assert len(country) == 2 and country.isupper()
        assert code.isdigit() and not code.startswith("0")


# ---------- properties (hypothesis, fixed seed: see conftest) ----------

bd_mobiles = st.builds(
    lambda op, rest: f"01{op}{rest}",
    st.sampled_from("3456789"),
    st.text(alphabet="0123456789", min_size=8, max_size=8),
)
separators = st.sampled_from(["", " ", "-", ".", "  "])


@given(st.text())
def test_any_text_never_raises(raw):
    result = normalize_phone(raw)
    assert result is None or result.startswith("+")


@given(st.text(alphabet="0123456789+ -().০১২৩৪৫৬৭৮৯", max_size=25))
def test_phone_like_text_never_raises(raw):
    normalize_phone(raw)


@given(st.text())
def test_accepted_numbers_normalize_to_themselves(raw):
    result = normalize_phone(raw)
    if result is not None:
        assert normalize_phone(result) == result


@given(bd_mobiles, separators, st.booleans())
def test_every_valid_mobile_survives_any_formatting(number, sep, bangla):
    formatted = sep.join([number[:3], number[3:7], number[7:]])
    if bangla:
        formatted = formatted.translate(str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯"))
    assert normalize_phone(formatted) == "+880" + number[1:]
