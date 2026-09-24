"""Phone numbers: any way a person types one → E.164 ('+8801712345678') or None.

normalize_phone never raises on user input; it returns None for anything that isn't
clearly a phone number. It does NOT pull numbers out of sentences: the caller passes
only the number. Local numbers (no + or 00) are read using the tenant's country.
"""

import re
import unicodedata

# Countries we serve or expect to (PRD §19). Calling code and national number length.
CALLING_CODES = {
    "BD": "880",
    "NP": "977",
    "IN": "91",
    "PK": "92",
    "LK": "94",
    "NG": "234",
    "MY": "60",
    "AE": "971",
    "SA": "966",
    "GB": "44",
    "US": "1",
    "CA": "1",
    "AU": "61",
}
NATIONAL_LENGTH = {  # digits after the calling code
    "880": (10, 10),
    "977": (8, 10),
    "91": (10, 10),
    "92": (9, 10),
    "94": (9, 9),
    "234": (8, 10),
    "60": (8, 10),
    "971": (8, 9),
    "966": (8, 9),
    "44": (9, 10),
    "1": (10, 10),
    "61": (9, 9),
}
BD_MOBILE = re.compile(r"^1[3-9][0-9]{8}$")  # after +880: operators 013-019
SEPARATORS = frozenset(" -.()")
MAX_INPUT = 64  # characters; anything longer isn't a phone number


def _digits(text: str) -> str | None:
    """ASCII digits from text in any script (Bangla, Devanagari, full-width...), or None."""
    out = []
    for ch in text:
        if ch in SEPARATORS:
            continue
        value = unicodedata.decimal(ch, None)  # superscripts etc. aren't decimal digits
        if value is None:
            return None
        out.append(str(value))
    return "".join(out)


def _valid(full: str) -> bool:
    """full: digits of an international number without '+'."""
    if not 8 <= len(full) <= 15 or full[0] == "0":
        return False
    for code in sorted(NATIONAL_LENGTH, key=len, reverse=True):
        if full.startswith(code):
            national = full[len(code) :]
            low, high = NATIONAL_LENGTH[code]
            if not low <= len(national) <= high:
                return False
            return code != "880" or bool(BD_MOBILE.match(national))
    return True  # a country we have no table for: general E.164 rules only


def normalize_phone(text, country: str = "BD") -> str | None:
    """Return '+<digits>' or None. Raises ValueError only for an unsupported tenant country."""
    if country not in CALLING_CODES:
        raise ValueError(f"unsupported country {country!r}")
    if not isinstance(text, str) or len(text) > MAX_INPUT:
        return None
    text = text.strip()
    plus = text.startswith("+")
    digits = _digits(text[1:] if plus else text)
    if not digits:
        return None
    code = CALLING_CODES[country]
    if plus:
        full = digits
    elif digits.startswith("00"):
        full = digits[2:]
    elif digits.startswith(code) and not digits.startswith("0"):
        full = digits  # international number typed without '+', e.g. 8801712345678
    elif digits.startswith("0"):
        full = code + digits[1:]  # drop the trunk 0 of a local number
    elif country == "BD":
        return None  # Bangladeshi local numbers always start with 0; anything else is a guess
    else:
        full = code + digits
    return "+" + full if _valid(full) else None
