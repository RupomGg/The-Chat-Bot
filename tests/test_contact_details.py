"""Contact-detail checks (P2.1b, D-015): clean value or None, never an exception on user input."""

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.contact_details import (
    normalize_country,
    normalize_email,
    normalize_https_url,
    normalize_name,
    normalize_year_month,
    valid_timezone,
)

JUNK = [None, 5, 3.2, ["a"], {"a": 1}, b"bytes", "", "   ", "\x00", "😀", "a" * 10_000]
DB_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # the database's own rule (migration 003)

# ---------- email ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("rahim@gmail.com", "rahim@gmail.com"),
        ("  Rahim@GMAIL.com  ", "Rahim@gmail.com"),  # domain lower-cased, local part kept
        ("rahim.uddin+visa@Consult.Com.BD", "rahim.uddin+visa@consult.com.bd"),
        ("a@b.co", "a@b.co"),
        ("user@münchen.de", "user@xn--mnchen-3ya.de"),  # international domain → ASCII form
        ("user@bücher.example", "user@xn--bcher-kva.example"),
        ("o'brien@example.ie", "o'brien@example.ie"),
        ("x@sub-domain.example.com", "x@sub-domain.example.com"),
    ],
)
def test_valid_emails(raw, expected):
    assert normalize_email(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "rahim",
        "rahim@",
        "@gmail.com",
        "rahim@gmail",  # no dot in the domain
        "a b@c.com",
        "a@@b.com",
        "a@b@c.com",
        "rahim@gmail..com",
        "rahim@.gmail.com",
        "rahim@gmail.com.",
        "rahim@-gmail.com",
        "rahim@gmail-.com",
        "rahim@gma_il.com",
        "rahim@gmail.c",  # one-letter top-level domain
        "rahim@gmail.123",  # numeric top-level domain
        ".rahim@gmail.com",
        "rahim.@gmail.com",
        "ra..him@gmail.com",
        "রহিম@gmail.com",  # non-ASCII local part: many mail systems refuse it
        "rahim@gmail.com\n",  # stripped, but a newline inside is not allowed:
        "rahim\n@gmail.com",
        "a" * 65 + "@gmail.com",  # local part over 64
        "a@" + "b" * 64 + ".com",  # a domain label over 63
        "a" * 10 + "@" + ("b" * 60 + ".") * 4 + "com",  # 258 characters: over 254
        "mailto:rahim@gmail.com",
        "<rahim@gmail.com>",
    ]
    + JUNK,
)
def test_invalid_emails(raw):
    if raw == "rahim@gmail.com\n":
        assert normalize_email(raw) == "rahim@gmail.com"  # surrounding whitespace is fine
    else:
        assert normalize_email(raw) is None


def test_email_exactly_254_characters_accepted():
    domain = ".".join(["d" * 60] * 4) + ".com"  # 244 characters
    email = "a" * (254 - len(domain) - 1) + "@" + domain
    assert len(email) == 254
    assert normalize_email(email) == email


@given(st.text())
def test_email_never_raises_and_matches_the_database_rule(raw):
    result = normalize_email(raw)
    if result is not None:
        assert DB_EMAIL.match(result) and len(result) <= 254
        assert normalize_email(result) == result


# ---------- name ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Rahim Uddin", "Rahim Uddin"),
        ("  Rahim    Uddin  ", "Rahim Uddin"),
        ("রহিম উদ্দিন", "রহিম উদ্দিন"),  # Bangla, incl. the hasanta conjunct
        ("Md. Rahim", "Md. Rahim"),
        ("O'Brien", "O'Brien"),
        ("Jean-Luc", "Jean-Luc"),
        ("José", "José"),
        ("José", "José"),  # decomposed accent → composed (NFC)
        ("राम", "राम"),  # Devanagari
        ("R", "R"),
        ("Rahim\tUddin", "Rahim Uddin"),  # tab between words becomes a space
    ],
)
def test_valid_names(raw, expected):
    assert normalize_name(raw) == expected


def test_bangla_joiners_are_kept():
    # Zero-width joiner/non-joiner (U+200D/U+200C) change how Bangla conjuncts render.
    name = "র\u200dযাব"
    assert normalize_name(name) == name


@pytest.mark.parametrize(
    "raw",
    [
        "😀😀",
        "Rahim 😀",
        "Rahim2",
        "12345",
        "Rahim@home",
        "<script>",
        "Rahim\x00",
        "...",
        "-",
        "a" * 101,
    ]
    + JUNK,
)
def test_invalid_names(raw):
    assert normalize_name(raw) is None


def test_name_length_boundary():
    assert normalize_name("a" * 100) == "a" * 100
    assert normalize_name("a" * 101) is None


@given(st.text())
def test_name_never_raises_and_is_stable(raw):
    result = normalize_name(raw)
    if result is not None:
        assert 1 <= len(result) <= 100 and result == result.strip() and "  " not in result
        assert normalize_name(result) == result


# ---------- country ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("BD", "BD"),
        ("bd", "BD"),
        (" Bangladesh ", "BD"),
        ("bangladesh", "BD"),
        ("বাংলাদেশ", "BD"),
        ("UK", "GB"),
        ("United Kingdom", "GB"),
        ("England", "GB"),
        ("GB", "GB"),
        ("USA", "US"),
        ("United States", "US"),
        ("America", "US"),
        ("Malaysia", "MY"),
        ("মালয়েশিয়া", "MY"),
        ("Hungary", "HU"),
        ("Cyprus", "CY"),
        ("UAE", "AE"),
        ("South Korea", "KR"),
        ("Korea", "KR"),
        ("FI", "FI"),
        ("NZ", "NZ"),
        ("ZW", "ZW"),  # any valid ISO code, even without an alias
    ],
)
def test_valid_countries(raw, expected):
    assert normalize_country(raw) == expected


@pytest.mark.parametrize("raw", ["ZZ", "XX", "B", "BGD", "Narnia", "U.K.", "Englnd"] + JUNK)
def test_invalid_countries(raw):
    assert normalize_country(raw) is None


# ---------- year-month ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2027-01", "2027-01"),
        ("2027-1", "2027-01"),
        ("2027/01", "2027-01"),
        ("01/2027", "2027-01"),
        ("1/2027", "2027-01"),
        ("01-2027", "2027-01"),
        ("Jan 2027", "2027-01"),
        ("january 2027", "2027-01"),
        ("JAN-2027", "2027-01"),
        ("2027 Jan", "2027-01"),
        ("Sept 2027", "2027-09"),
        ("September 2027", "2027-09"),
        ("জানুয়ারি ২০২৭", "2027-01"),
        ("সেপ্টেম্বর ২০২৭", "2027-09"),
        ("২০২৭-০৯", "2027-09"),
        ("December 2099", "2099-12"),
        ("2000-01", "2000-01"),
    ],
)
def test_valid_year_months(raw, expected):
    assert normalize_year_month(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "2027-13",
        "2027-00",
        "13/2027",
        "0/2027",
        "Jan 27",  # two-digit year is ambiguous
        "Janu 2027",
        "2027",
        "January",
        "1999-12",  # before 2000
        "2101-01",  # after 2100
        "2027-01-15",  # a full date, not a month
        "next january",
        "September intake 2027",  # extra words: the AI passes the value only
    ]
    + JUNK,
)
def test_invalid_year_months(raw):
    assert normalize_year_month(raw) is None


@given(st.text())
def test_year_month_never_raises_and_is_stable(raw):
    result = normalize_year_month(raw)
    if result is not None:
        assert re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])|2100-(0[1-9]|1[0-2])", result)
        assert normalize_year_month(result) == result


# ---------- timezone ----------


@pytest.mark.parametrize(
    "name", ["Asia/Dhaka", "Europe/London", "Asia/Kathmandu", "UTC", "America/New_York"]
)
def test_valid_timezones(name):
    assert valid_timezone(name) is True


@pytest.mark.parametrize(
    "name",
    ["Dhaka", "asia/dhaka", "Asia/Dhakka", "GMT+6", "+06:00", "../etc/passwd", "Asia/"] + JUNK,
)
def test_invalid_timezones(name):
    assert valid_timezone(name) is False


# ---------- https URL ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://maps.google.com/?q=Banani", "https://maps.google.com/?q=Banani"),
        ("HTTPS://Consult.COM.bd/about", "https://consult.com.bd/about"),
        ("  https://example.com  ", "https://example.com"),
        ("https://example.com:8443/x", "https://example.com:8443/x"),
        ("https://consult.com.bd/courses?c=uk#fees", "https://consult.com.bd/courses?c=uk#fees"),
        ("https://Consult.com.bd#top", "https://consult.com.bd#top"),
        ("https://বাংলা.com/path", "https://xn--54b7fta0cc.com/path"),
    ],
)
def test_valid_urls(raw, expected):
    assert normalize_https_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "http://example.com",  # not https
        "javascript:alert(1)",
        "data:text/html,<script>",
        "ftp://example.com",
        "https://",
        "https:///path",
        "https://user:pass@example.com",  # credentials in the link
        "https://example",  # no dot in the host
        "https://exa mple.com",
        "https://example.com/\nx",
        "//example.com",
        "example.com",
        "https://example.com:99999",
        "https://" + "a" * 2100 + ".com",
    ]
    + JUNK,
)
def test_invalid_urls(raw):
    assert normalize_https_url(raw) is None


@given(st.text())
def test_url_never_raises(raw):
    result = normalize_https_url(raw)
    assert result is None or result.startswith("https://")
