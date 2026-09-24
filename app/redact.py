"""Sensitive-data redaction (PRD §9.5): card, national ID (NID) and passport numbers are
replaced before a message is stored or sent to the AI. Phone numbers are kept on purpose
(D-014) and money amounts are left alone.

Digits of any script count (Bangla ০-৯ too). Redacting twice gives the same text.
"""

import re
import unicodedata

from app.phones import normalize_phone

CARD, NID, PASSPORT = "[card]", "[nid]", "[passport]"
NID_LENGTHS = (10, 13, 17)
CARD_LENGTHS = range(13, 20)

# Runs of digits, optionally split by single spaces or dashes: "4111 1111-1111 1111".
RUN = re.compile("(?<![0-9])[0-9]+(?:[ -][0-9]+)*(?![0-9])")
# One or two letters then 7-8 digits, standing alone: "A12345678", "BX1234567".
PASSPORT_LIKE = re.compile("(?<![A-Za-z0-9])[A-Za-z]{1,2}[0-9]{7,8}(?![A-Za-z0-9])")
SEPARATOR = re.compile("[ -]")


def _ascii_digits(text: str) -> str:
    """Same length, every decimal digit of any script as 0-9, so match positions line up."""
    return "".join(
        str(unicodedata.decimal(ch)) if unicodedata.decimal(ch, None) is not None else ch
        for ch in text
    )


def _luhn(digits: str) -> bool:
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def _is_card(digits: str) -> bool:
    return len(digits) in CARD_LENGTHS and _luhn(digits)


def _card_grouping(pieces: list[str]) -> bool:
    """How cards are written: 4-4-4-4(-3), or 4-6-5 / 4-6-4. Anything else is several numbers."""
    sizes = [len(p) for p in pieces]
    if sizes[:1] == [4] and sizes[1:2] == [6] and len(sizes) == 3 and sizes[2] in (4, 5):
        return True
    return all(s == 4 for s in sizes[:-1]) and 1 <= sizes[-1] <= 4


def _is_phone(digits: str) -> bool:
    return normalize_phone(digits, "BD") is not None


def _run_spans(run: re.Match) -> list[tuple[int, int, str]]:
    """What to redact inside one run of digits: all of it, some pieces, or nothing."""
    pieces = SEPARATOR.split(run.group())
    joined = "".join(pieces)
    if _is_phone(joined):
        return []  # e.g. "+880 1712-345678": kept on purpose
    has_phone = any(_is_phone(p) for p in pieces)  # "12 01712345678" is two numbers
    if _is_card(joined) and (len(pieces) == 1 or _card_grouping(pieces)):  # no phone fits
        return [(run.start(), run.end(), CARD)]
    spaced_nid = len(pieces) > 1 and all(len(p) >= 3 for p in pieces)  # not "2024 2025 20"
    if not has_phone and spaced_nid and len(joined) in NID_LENGTHS:
        return [(run.start(), run.end(), NID)]  # an NID typed with spaces
    spans, pos = [], run.start()
    for piece in pieces:
        if _is_phone(piece):
            pass
        elif _is_card(piece):
            spans.append((pos, pos + len(piece), CARD))
        elif len(piece) in NID_LENGTHS:
            spans.append((pos, pos + len(piece), NID))
        pos += len(piece) + 1
    return spans


def redact(text: str) -> str:
    """Text with card, NID and passport numbers replaced by [card], [nid], [passport]."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    ascii_text = _ascii_digits(text)
    spans = [(m.start(), m.end(), PASSPORT) for m in PASSPORT_LIKE.finditer(ascii_text)]
    for run in RUN.finditer(ascii_text):
        if not any(start < run.end() and run.start() < end for start, end, _ in spans):
            spans.extend(_run_spans(run))
    out, last = [], 0
    for start, end, label in sorted(spans):
        out.append(text[last:start])
        out.append(label)
        last = end
    out.append(text[last:])
    return "".join(out)
