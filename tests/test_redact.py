"""Sensitive-data redaction (P2.5, PRD §9.5)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.redact import CARD, _luhn, redact


def with_check_digit(body: str) -> str:
    """Append the digit that makes `body` pass the Luhn check (a valid-looking card)."""
    return next(body + d for d in "0123456789" if _luhn(body + d))


# ---------- cards ----------


@pytest.mark.parametrize(
    "card",
    [
        "4111111111111111",  # Visa test number
        "5555555555554444",  # Mastercard
        "378282246310005",  # Amex (15)
        "4222222222222",  # 13 digits
        with_check_digit("601100099013942"),  # 16
        with_check_digit("123456789012345678"),  # 19
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
        "3782 822463 10005",  # Amex grouping
        "৪১১১ ১১১১ ১১১১ ১১১১",  # Bangla digits
    ],
)
def test_valid_cards_are_redacted(card):
    assert redact(f"my card {card} thanks") == "my card [card] thanks"


@pytest.mark.parametrize(
    "number",
    [
        "4111111111111112",  # 16 digits, fails the Luhn check
        "411111111111",  # 12 digits: too short for a card
        with_check_digit("12345678901234567890")[:20],  # 20 digits: too long
    ],
)
def test_card_like_numbers_that_arent_cards_are_kept(number):
    assert redact(number) == number


@pytest.mark.parametrize(
    "text, expected",
    [
        ("qty 2 4111111111111111", "qty 2 [card]"),
        ("1234 4111111111111111", "1234 [card]"),
        ("4111111111111111 1234567890", "[card] [nid]"),
    ],
)
def test_card_next_to_another_number(text, expected):
    assert redact(text) == expected


def split(number, *sizes):
    """Write `number` in pieces of the given sizes, joined by spaces."""
    pieces, pos = [], 0
    for size in sizes:
        pieces.append(number[pos : pos + size])
        pos += size
    return " ".join(pieces)


@pytest.mark.parametrize(
    "sizes",
    [
        (6, 7),  # two money amounts side by side: "150000 2500001"
        (4, 12),  # a year and a 12-digit amount
        (2, 13, 1),
    ],
)
def test_numbers_that_happen_to_pass_the_card_check_but_arent_written_like_a_card(sizes):
    number = with_check_digit("150000250000" + "0" * (sum(sizes) - 13))
    assert len(number) == sum(sizes) and _luhn(number)
    text = split(number, *sizes)
    assert CARD not in redact(text)


# ---------- NID ----------


@pytest.mark.parametrize(
    "nid",
    [
        "1234567890",  # 10 (smart card)
        "1234567890123",  # 13 (old)
        "19901234567890123",  # 17 (with birth year)
        "১২৩৪৫৬৭৮৯০",  # Bangla digits
        "1234 567 890",  # typed with spaces
        "123-456-7890",
    ],
)
def test_nid_numbers_are_redacted(nid):
    assert redact(f"NID: {nid}.") == "NID: [nid]."


@pytest.mark.parametrize("number", ["123456789", "12345678901", "123456789012", "12345678901234"])
def test_other_lengths_are_not_nid(number):
    assert redact(number) == number


def test_years_with_spaces_are_not_an_nid():
    assert redact("intake 2026 2027 20") == "intake 2026 2027 20"


# ---------- passports ----------


@pytest.mark.parametrize(
    "passport", ["A12345678", "BX1234567", "a1234567", "EB0123456", "A১২৩৪৫৬৭৮"]
)
def test_passport_like_numbers_are_redacted(passport):
    assert redact(f"passport {passport}, valid") == "passport [passport], valid"


@pytest.mark.parametrize(
    "text",
    [
        "ABC1234567",  # three letters
        "A123456",  # six digits
        "A123456789",  # nine digits
        "A1234567B",  # glued to a letter
        "HSC2024",
        "IELTS 7.5",
        "B2 visa",
    ],
)
def test_passport_look_alikes_are_kept(text):
    assert redact(text) == text


# ---------- kept on purpose ----------


@pytest.mark.parametrize(
    "phone",
    [
        "01712345678",
        "+8801712345678",
        "8801712345678",  # 13 digits like an old NID, but a valid phone: kept (D-014)
        "008801712345678",
        "+880 1712-345678",
        "01712 345678",
        "০১৭১২৩৪৫৬৭৮",
    ],
)
def test_bangladesh_phone_numbers_are_kept(phone):
    assert redact(f"call me on {phone} today") == f"call me on {phone} today"


@pytest.mark.parametrize(
    "text",
    [
        "12 01712345678",
        "1234 01712345678 99",
        "123456 01712345678",  # 17 digits together, like a new NID
        "12 8801712345678",  # 13-digit phone, like an old NID
    ],
)
def test_phone_next_to_other_numbers_is_kept(text):
    assert redact(text) == text


def test_passport_followed_by_a_number_is_redacted_once():
    assert redact("A1234567 123") == "[passport] 123"


@pytest.mark.parametrize(
    "money",
    [
        "15,00,000 taka",
        "1500000",
        "1,500,000",
        "৳১৫,০০,০০০",
        "Tk 2,50,000/-",
        "fees 1500000 taka per year",
        "GBP 18,500.50",
    ],
)
def test_money_amounts_are_kept(money):
    assert redact(money) == money


@pytest.mark.parametrize(
    "text",
    ["2026-09-24", "10:30-11:30", "IELTS 6.5; gap 2 years", "GPA 4.50", "HSC 2022, SSC 2020", ""],
)
def test_ordinary_messages_are_unchanged(text):
    assert redact(text) == text


# ---------- several, idempotent, input ----------


def test_several_items_are_all_redacted():
    text = "card 4111111111111111, nid 1234567890, passport A1234567, phone 01712345678"
    assert redact(text) == "card [card], nid [nid], passport [passport], phone 01712345678"


def test_redacting_twice_changes_nothing_more():
    once = redact("4111 1111 1111 1111 and A1234567")
    assert redact(once) == once


@pytest.mark.parametrize("text", [None, 5, b"4111111111111111", ["x"]])
def test_only_text_is_accepted(text):
    with pytest.raises(TypeError):
        redact(text)


@given(st.text())
def test_never_raises_and_is_idempotent(text):
    once = redact(text)
    assert redact(once) == once


bd_phones = st.builds(
    lambda third, rest: "01" + third + rest,
    st.sampled_from("3456789"),
    st.text(alphabet="0123456789", min_size=8, max_size=8),
)


@given(st.text(), bd_phones, st.text())
def test_a_phone_anywhere_in_random_text_survives(before, phone, after):
    assert phone in redact(f"{before} {phone} {after}")
