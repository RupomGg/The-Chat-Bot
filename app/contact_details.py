"""Contact details for international use (D-015): email, name, country, year-month,
timezone, https URL. Each function returns a clean value or None (or False for
valid_timezone) and never raises on user input.
"""

import functools
import re
import unicodedata
import zoneinfo
from urllib.parse import urlsplit

# ---------- shared helpers ----------


def _has_control_or_space(text: str) -> bool:
    return any(ch.isspace() or unicodedata.category(ch) in ("Cc", "Cf") for ch in text)


def _ascii_host(host: str) -> str | None:
    """Lower-case, IDNA-encode (münchen.de → xn--mnchen-3ya.de) and check every label."""
    try:
        ascii_host = host.lower().encode("idna").decode("ascii")
    except UnicodeError:
        return None
    labels = ascii_host.split(".")
    if len(labels) < 2 or not all(HOST_LABEL.match(label) for label in labels):
        return None
    if not (TLD.match(labels[-1]) or labels[-1].startswith("xn--")):
        return None
    return ascii_host


HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
TLD = re.compile(r"^[a-z]{2,63}$")

# ---------- email ----------

EMAIL_LOCAL = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$")
MAX_EMAIL = 254
MAX_LOCAL = 64


def normalize_email(text) -> str | None:
    """'  Rahim@GMAIL.com ' → 'Rahim@gmail.com'. Local part kept as typed; ASCII only."""
    if not isinstance(text, str) or len(text) > 4 * MAX_EMAIL:
        return None
    text = text.strip()
    if _has_control_or_space(text) or text.count("@") != 1:
        return None
    local, domain = text.split("@")
    if not (1 <= len(local) <= MAX_LOCAL) or not EMAIL_LOCAL.match(local):
        return None
    ascii_domain = _ascii_host(domain)
    if ascii_domain is None:
        return None
    email = f"{local}@{ascii_domain}"
    return email if len(email) <= MAX_EMAIL else None


# ---------- name ----------

NAME_PUNCTUATION = frozenset(".'-’")
JOINERS = frozenset("\u200c\u200d")  # shape Bangla conjuncts; not invisible junk
MAX_NAME = 100


def normalize_name(text) -> str | None:
    """Trim, collapse spaces, NFC. Letters of any script, marks, and . ' - only."""
    if not isinstance(text, str) or len(text) > 4 * MAX_NAME:
        return None
    name = " ".join(unicodedata.normalize("NFC", text).split())
    if not 1 <= len(name) <= MAX_NAME:
        return None
    has_letter = False
    for ch in name:
        category = unicodedata.category(ch)
        if category.startswith("L"):
            has_letter = True
        elif not (category.startswith("M") or ch == " " or ch in NAME_PUNCTUATION or ch in JOINERS):
            return None
    return name if has_letter else None


# ---------- country ----------

ISO_COUNTRIES = frozenset(
    [
        "AD",
        "AE",
        "AF",
        "AG",
        "AI",
        "AL",
        "AM",
        "AO",
        "AQ",
        "AR",
        "AS",
        "AT",
        "AU",
        "AW",
        "AX",
        "AZ",
        "BA",
        "BB",
        "BD",
        "BE",
        "BF",
        "BG",
        "BH",
        "BI",
        "BJ",
        "BL",
        "BM",
        "BN",
        "BO",
        "BQ",
        "BR",
        "BS",
        "BT",
        "BV",
        "BW",
        "BY",
        "BZ",
        "CA",
        "CC",
        "CD",
        "CF",
        "CG",
        "CH",
        "CI",
        "CK",
        "CL",
        "CM",
        "CN",
        "CO",
        "CR",
        "CU",
        "CV",
        "CW",
        "CX",
        "CY",
        "CZ",
        "DE",
        "DJ",
        "DK",
        "DM",
        "DO",
        "DZ",
        "EC",
        "EE",
        "EG",
        "EH",
        "ER",
        "ES",
        "ET",
        "FI",
        "FJ",
        "FK",
        "FM",
        "FO",
        "FR",
        "GA",
        "GB",
        "GD",
        "GE",
        "GF",
        "GG",
        "GH",
        "GI",
        "GL",
        "GM",
        "GN",
        "GP",
        "GQ",
        "GR",
        "GS",
        "GT",
        "GU",
        "GW",
        "GY",
        "HK",
        "HM",
        "HN",
        "HR",
        "HT",
        "HU",
        "ID",
        "IE",
        "IL",
        "IM",
        "IN",
        "IO",
        "IQ",
        "IR",
        "IS",
        "IT",
        "JE",
        "JM",
        "JO",
        "JP",
        "KE",
        "KG",
        "KH",
        "KI",
        "KM",
        "KN",
        "KP",
        "KR",
        "KW",
        "KY",
        "KZ",
        "LA",
        "LB",
        "LC",
        "LI",
        "LK",
        "LR",
        "LS",
        "LT",
        "LU",
        "LV",
        "LY",
        "MA",
        "MC",
        "MD",
        "ME",
        "MF",
        "MG",
        "MH",
        "MK",
        "ML",
        "MM",
        "MN",
        "MO",
        "MP",
        "MQ",
        "MR",
        "MS",
        "MT",
        "MU",
        "MV",
        "MW",
        "MX",
        "MY",
        "MZ",
        "NA",
        "NC",
        "NE",
        "NF",
        "NG",
        "NI",
        "NL",
        "NO",
        "NP",
        "NR",
        "NU",
        "NZ",
        "OM",
        "PA",
        "PE",
        "PF",
        "PG",
        "PH",
        "PK",
        "PL",
        "PM",
        "PN",
        "PR",
        "PS",
        "PT",
        "PW",
        "PY",
        "QA",
        "RE",
        "RO",
        "RS",
        "RU",
        "RW",
        "SA",
        "SB",
        "SC",
        "SD",
        "SE",
        "SG",
        "SH",
        "SI",
        "SJ",
        "SK",
        "SL",
        "SM",
        "SN",
        "SO",
        "SR",
        "SS",
        "ST",
        "SV",
        "SX",
        "SY",
        "SZ",
        "TC",
        "TD",
        "TF",
        "TG",
        "TH",
        "TJ",
        "TK",
        "TL",
        "TM",
        "TN",
        "TO",
        "TR",
        "TT",
        "TV",
        "TW",
        "TZ",
        "UA",
        "UG",
        "UM",
        "US",
        "UY",
        "UZ",
        "VA",
        "VC",
        "VE",
        "VG",
        "VI",
        "VN",
        "VU",
        "WF",
        "WS",
        "YE",
        "YT",
        "ZA",
        "ZM",
        "ZW",
    ]
)
# Common names for countries our clients deal with (sources and study destinations).
COUNTRY_ALIASES = {
    "bangladesh": "BD",
    "বাংলাদেশ": "BD",
    "nepal": "NP",
    "india": "IN",
    "pakistan": "PK",
    "sri lanka": "LK",
    "nigeria": "NG",
    "uk": "GB",
    "united kingdom": "GB",
    "great britain": "GB",
    "britain": "GB",
    "england": "GB",
    "যুক্তরাজ্য": "GB",
    "usa": "US",
    "us": "US",
    "united states": "US",
    "america": "US",
    "যুক্তরাষ্ট্র": "US",
    "canada": "CA",
    "কানাডা": "CA",
    "australia": "AU",
    "অস্ট্রেলিয়া": "AU",
    "new zealand": "NZ",
    "malaysia": "MY",
    "মালয়েশিয়া": "MY",
    "ireland": "IE",
    "germany": "DE",
    "jarmani": "DE",
    "france": "FR",
    "italy": "IT",
    "hungary": "HU",
    "finland": "FI",
    "cyprus": "CY",
    "sweden": "SE",
    "denmark": "DK",
    "netherlands": "NL",
    "poland": "PL",
    "japan": "JP",
    "china": "CN",
    "south korea": "KR",
    "korea": "KR",
    "turkey": "TR",
    "turkiye": "TR",
    "uae": "AE",
    "united arab emirates": "AE",
    "dubai": "AE",
    "saudi arabia": "SA",
    "singapore": "SG",
}


def normalize_country(text) -> str | None:
    """ISO 3166-1 alpha-2 code from a code or a common name: 'Bangladesh' / 'bd' → 'BD'."""
    if not isinstance(text, str) or len(text) > 60:
        return None
    key = " ".join(unicodedata.normalize("NFC", text).split()).lower()
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]
    code = key.upper()
    return code if code in ISO_COUNTRIES else None


# ---------- year-month ----------

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
    "জানুয়ারি": 1,
    "ফেব্রুয়ারি": 2,
    "মার্চ": 3,
    "এপ্রিল": 4,
    "মে": 5,
    "জুন": 6,
    "জুলাই": 7,
    "আগস্ট": 8,
    "সেপ্টেম্বর": 9,
    "অক্টোবর": 10,
    "নভেম্বর": 11,
    "ডিসেম্বর": 12,
}
MONTHS = {unicodedata.normalize("NFC", name): number for name, number in _MONTHS.items()}
YEAR_RANGE = (2000, 2100)
_WORD = r"([a-zঀ-৿]+)"
YM_PATTERNS = (
    (re.compile(r"^(\d{4})[-/](\d{1,2})$"), "year", "month"),
    (re.compile(r"^(\d{1,2})[-/](\d{4})$"), "month", "year"),
    (re.compile(rf"^{_WORD}[\s-]+(\d{{4}})$"), "name", "year"),
    (re.compile(rf"^(\d{{4}})[\s-]+{_WORD}$"), "year", "name"),
)


def normalize_year_month(text) -> str | None:
    """'Jan 2027', '01/2027', 'জানুয়ারি ২০২৭' → '2027-01'. Years 2000-2100 only."""
    if not isinstance(text, str) or len(text) > 40:
        return None
    # \d and int() already understand Bangla and other scripts' digits: "২০২৭" → 2027.
    value = unicodedata.normalize("NFC", text).strip().lower()
    for pattern, first, second in YM_PATTERNS:
        match = pattern.match(value)
        if not match:
            continue
        parts = dict(zip((first, second), match.groups(), strict=True))
        month = MONTHS.get(parts["name"]) if "name" in parts else int(parts["month"])
        year = int(parts["year"])
        if month and 1 <= month <= 12 and YEAR_RANGE[0] <= year <= YEAR_RANGE[1]:
            return f"{year:04d}-{month:02d}"
        return None
    return None


# ---------- timezone ----------


@functools.cache
def _timezones() -> frozenset:
    return frozenset(zoneinfo.available_timezones())


def valid_timezone(name) -> bool:
    """IANA name such as 'Asia/Dhaka' (exact spelling)."""
    return isinstance(name, str) and name in _timezones()


# ---------- https URL ----------

MAX_URL = 2048


def normalize_https_url(text) -> str | None:
    """https only, a real host, no credentials, no spaces. Scheme and host lower-cased."""
    if not isinstance(text, str) or len(text) > MAX_URL:
        return None
    text = text.strip()
    if _has_control_or_space(text):
        return None
    parts = urlsplit(text)
    if parts.scheme.lower() != "https" or "@" in parts.netloc or not parts.hostname:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    host = _ascii_host(parts.hostname)
    if host is None:
        return None
    url = "https://" + host + (f":{port}" if port else "") + parts.path
    if parts.query:
        url += "?" + parts.query
    if parts.fragment:
        url += "#" + parts.fragment
    return url
