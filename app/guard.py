"""Abuse guards (D-018, D-019): nobody uses the bot as a free general AI.

check_input runs before any model call and costs nothing; check_reply runs on the model's
reply before it is sent. Each returns None (fine) or a short reason. A real customer
question must never be blocked, so every pattern is narrow; the AI's own rules and the
eval set are the next layers.
"""

import re

from app.quick_answers import fold_text

MAX_REPLY_CHARS = 2000  # Messenger's limit, the smallest of our channels

# ---------- code ----------

CODE_LINE_STARTS = (
    "def ",
    "class ",
    "import ",
    "#include",
    "public static",
    "private static",
    "function ",
    "const ",
    "let ",
    "var ",
    "console.log",
    "system.out",
    "print(",
    "printf(",
    "return ",
    "for (",
    "for(",
    "while (",
    "while(",
    "if (",
    "if(",
    "elif ",
    "#!/",
    "<?php",
    "<script",
)
SQL = re.compile("select .+ from |insert into |update .+ set |delete from |create table ")
SQL_CLAUSE = re.compile(
    "^(?:where .*[=<>]|order by |group by |having |(?:inner |left )?join |values ?[(])"
)
LIST_ITEM = re.compile("^(?:[-*•]|[0-9]+[.)]) ")  # an indented bullet is not code
TAB = chr(9)


def _looks_like_code_line(raw: str) -> bool:
    line = raw.strip().lower()
    if not line:
        return False
    return (
        (raw.startswith(("    ", TAB)) and not LIST_ITEM.match(line))  # indented code body
        or line.startswith(CODE_LINE_STARTS)
        or SQL_CLAUSE.match(line) is not None
        or line.endswith(("{", "}"))
        or (line.endswith(";") and any(c in line for c in "(=["))  # not "Name: Rahim;"
        or SQL.search(line + " ") is not None
    )


def _looks_like_code(text: str) -> bool:
    if "```" in text:
        return True
    if sum(_looks_like_code_line(line) for line in text.splitlines()) >= 3:
        return True
    # A pasted one-liner: braces and semicolons together, or a code start with a semicolon.
    if "{" in text and "}" in text and text.count(";") >= 2:
        return True
    return any(
        line.strip().lower().startswith(CODE_LINE_STARTS) and ";" in line
        for line in text.splitlines()
    )


# ---------- encoded blobs ----------

BLOB = re.compile("[A-Za-z0-9+/=_-]{200,}")  # base64, base64url or hex, 200+ characters

# ---------- jailbreak phrases (matched on fold_text output: lower-case, single spaces) ----------

_ANY = "(?:all |any |the |every |previous |prior |above |earlier |your |of |these |those |my )*"
_RULES = "(?:instructions?|rules?|prompts?|guidelines?|directions?|training)"
_AI = (
    "(?:ai|assistant|chatbot|bot|chatgpt|gpt|llm|language model|terminal|linux|"
    "developer|programmer|coder|hacker|dan)"
)
ENGLISH = (
    f"(?:ignore|forget|disregard|override|bypass) {_ANY}{_RULES}",
    "system prompt",
    "developer mode",
    "dev mode",
    "jailbreak(?:ed|ing)?",
    "jailbroken",
    "dan mode",
    "do anything now",
    "you are now (?:a|an|in|my|chatgpt|gpt|dan|free|unrestricted|jailbroken|developer)",
    "(?:you re|you are) (?:no longer|not) (?:an? )?(?:assistant|bot|restricted)",
    "pretend (?:you are|you re|that you are)",  # not "can I pretend to be employed"
    f"act as (?:a |an |my |the )?(?:[^ ]+ ){{0,2}}{_AI}",
    "role ?play",
    # Found by the P4.5 demo run: another word order, and plain requests for code.
    "(?:you are|you re) (?:now )?(?:chatgpt|gpt|gemini|claude|dan)",
    "(?:write|fix|debug|solve|explain|build) (?:me |my |this |a |an |the |some )*"
    "(?:[^ ]+ ){0,2}(?:code|python|java|javascript|sql|function|algorithm|script)",
    "repeat (?:the |all |everything |your )?(?:text |words |instructions |prompt )?above",
    "(?:print|show|reveal|tell me|output|display|give me) (?:me )?(?:your|the) (?:system )?"
    "(?:prompt|instructions)",  # not "tell me the rules for dependants"
)
BANGLISH = (
    "(?:sob |sokol |ager )?(?:niyom|nirdesh|nirdeshona|instructions?|rules?)"
    "(?: gula| guli| gulo)? "
    "(?:bhule jao|bhule jan|ignore koro|ignore koren|baad dao|mene cholo na)",
)
BANGLA_ITEMS = ("নির্দেশনা", "নির্দেশ", "নিয়ম", "নিয়মগুলো", "নিয়মগুলি", "রুলস", "ইনস্ট্রাকশন")
BANGLA_ACTIONS = ("ভুলে যাও", "ভুলে যান", "উপেক্ষা করো", "উপেক্ষা করুন", "মানবে না", "মেনো না")


def _alternatives(words) -> str:
    return "(?:" + "|".join(re.escape(fold_text(w)) for w in words) + ")"


BANGLA = (f"{_alternatives(BANGLA_ITEMS)}(?: গুলো| গুলি)? {_alternatives(BANGLA_ACTIONS)}",)
JAILBREAK = re.compile("(?:^| )(?:" + "|".join(ENGLISH + BANGLISH + BANGLA) + ")(?= |$)")


def _join_spaced_letters(folded: str) -> str:
    """'i g n o r e your rules' → 'ignore your rules' (3+ single letters in a row)."""
    words, run = [], []
    for token in [*folded.split(" "), ""]:
        if len(token) == 1:
            run.append(token)
            continue
        words.extend(["".join(run)] if len(run) >= 3 else run)
        run = []
        words.append(token)
    return " ".join(w for w in words if w)


# ---------- checks ----------


def check_input(text: str) -> str | None:
    """Why this customer message must not reach the AI ('code', 'encoded', 'jailbreak'),
    or None. Hidden characters, odd spacing, capitals and line breaks don't hide a phrase."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if _looks_like_code(text):
        return "code"
    if BLOB.search(text):
        return "encoded"
    folded = fold_text(text)
    if JAILBREAK.search(folded) or JAILBREAK.search(_join_spaced_letters(folded)):
        return "jailbreak"
    return None


def check_reply(text: str, *, max_chars: int = MAX_REPLY_CHARS) -> str | None:
    """Why the AI's reply must not be sent ('code', 'too_long'), or None."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if _looks_like_code(text):
        return "code"
    if len(text) > max_chars:
        return "too_long"
    return None
