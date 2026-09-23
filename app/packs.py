"""Industry packs (D-012): everything industry-specific lives in packs/<name>/, never in code.

A pack is pack.toml (fields to collect, lead-scoring rules, stage labels, tenant settings),
prompt.md (bot instructions template) and knowledge_template.md. load_pack() reads and fully
validates a pack, listing every problem at once, so a broken pack can't reach a tenant.
Scoring rules are only checked here; P2.3 evaluates them.
"""

import dataclasses
import re
import tomllib
from pathlib import Path

PACKS_DIR = Path(__file__).resolve().parent.parent / "packs"
PACK_NAME = re.compile(r"^[a-z][a-z_]{1,39}$")  # same rule as tenants.industry
IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
LANG = re.compile(r"^[a-z]{2}$")
FILES = ("pack.toml", "prompt.md", "knowledge_template.md")

GENERIC_STAGES = ("new", "contacted", "qualified", "booked", "in_progress", "won", "lost")
FIELD_TYPES = ("text", "int", "bool", "choice", "list", "yearmonth")
PRIORITIES = ("high", "medium", "low")
SETTING_TYPES = ("list", "text", "int")
BUILTIN_FIELDS = {"phone": "phone", "name": "text", "adult": "bool"}  # contact columns
PROMPT_PLACEHOLDERS = {"business_name", "knowledge_markdown"}

OPS_BY_TYPE = {
    "text": {"present", "absent", "eq", "ne", "in", "not_in"},
    "choice": {"present", "absent", "eq", "ne", "in", "not_in"},
    "int": {"present", "absent", "eq", "ne", "gte", "lte"},
    "bool": {"present", "absent", "eq", "ne"},
    "list": {"present", "absent", "overlaps_setting"},
    "yearmonth": {"present", "absent", "within_months"},
    "phone": {"present", "absent"},
}
ALL_OPS = set().union(*OPS_BY_TYPE.values())
OP_ARGS = {
    "present": set(),
    "absent": set(),
    "eq": {"value"},
    "ne": {"value"},
    "in": {"values"},
    "not_in": {"values"},
    "gte": {"value"},
    "lte": {"value"},
    "within_months": {"months"},
    "overlaps_setting": {"setting"},
}


class PackError(Exception):
    """The pack is missing, unreadable or invalid. The message lists every problem."""


@dataclasses.dataclass(frozen=True)
class Field:
    name: str
    type: str
    priority: str
    label: dict
    choices: tuple = ()


@dataclasses.dataclass(frozen=True)
class Condition:
    field: str | None = None
    op: str | None = None
    value: object = None
    values: tuple = ()
    months: int | None = None
    setting: str | None = None
    any: tuple = ()  # of Condition: true if any of them holds


@dataclasses.dataclass(frozen=True)
class Flag:
    name: str
    when: tuple  # of Condition, all must hold


@dataclasses.dataclass(frozen=True)
class Scoring:
    hot: tuple
    warm: tuple
    flags: tuple


@dataclasses.dataclass(frozen=True)
class Pack:
    name: str
    display_name: str
    version: int
    stages: dict
    fields: tuple
    scoring: Scoring
    tenant_settings: dict
    prompt: str
    knowledge_template: str


def _is_text(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class _Checker:
    """Collects problems instead of stopping at the first one."""

    def __init__(self):
        self.problems: list[str] = []

    def add(self, where: str, message: str) -> None:
        self.problems.append(f"{where}: {message}")

    def keys(self, where, table, allowed, required=()):
        for key in table:
            if key not in allowed:
                self.add(where, f"unknown key '{key}'")
        for key in required:
            if key not in table:
                self.add(where, f"missing key '{key}'")

    def labels(self, where, labels) -> dict:
        if not isinstance(labels, dict):
            self.add(where, "must be a table of language = label")
            return {}
        for lang, text in labels.items():
            if not LANG.match(lang):
                self.add(where, f"bad language code '{lang}'")
            elif not _is_text(text):
                self.add(where, f"label '{lang}' must be non-empty text")
        if "en" not in labels:
            self.add(where, "needs an 'en' label")
        return dict(labels)

    def stages(self, table) -> dict:
        if not isinstance(table, dict):
            self.add("stages", "must be a table")
            return {}
        for stage in GENERIC_STAGES:
            if stage not in table:
                self.add("stages", f"missing '{stage}'")
        for stage in table:
            if stage not in GENERIC_STAGES:
                self.add("stages", f"unknown '{stage}'")
        return {s: self.labels(f"stages.{s}", table[s]) for s in GENERIC_STAGES if s in table}

    def fields(self, items) -> tuple:
        if not isinstance(items, list) or not items:
            self.add("fields", "at least one field is required")
            return ()
        result, seen = [], set()
        for i, item in enumerate(items):
            name = item.get("name", "") if isinstance(item, dict) else ""
            where = f"fields.{name}" if name else f"fields[{i}]"
            if not isinstance(item, dict):
                self.add(where, "must be a table")
                continue
            self.keys(
                where,
                item,
                {"name", "type", "priority", "label", "choices"},
                ("name", "type", "priority", "label"),
            )
            if not isinstance(name, str) or not IDENT.match(name):
                self.add(where, f"invalid field name {name!r}")
                continue
            if name in BUILTIN_FIELDS:
                self.add(where, f"'{name}' is built in; don't declare it")
                continue
            if name in seen:
                self.add("fields", f"duplicate '{name}'")
                continue
            seen.add(name)
            ftype = item.get("type")
            if ftype not in FIELD_TYPES:
                self.add(where, f"unknown type '{ftype}'")
            if item.get("priority") not in PRIORITIES:
                self.add(where, "priority must be high, medium or low")
            choices = item.get("choices")
            if ftype == "choice":
                if not isinstance(choices, list) or not choices or not all(map(_is_text, choices)):
                    self.add(where, "a choice field needs 'choices' (non-empty text values)")
                    choices = []
                elif len(set(choices)) != len(choices):
                    self.add(where, "choices must be unique")
            elif choices is not None:
                self.add(where, "only choice fields have 'choices'")
                choices = []
            label = self.labels(f"{where}.label", item.get("label", {}))
            result.append(Field(name, ftype, item.get("priority"), label, tuple(choices or ())))
        return tuple(result)

    def settings(self, table) -> dict:
        if not isinstance(table, dict):
            self.add("tenant_settings", "must be a table")
            return {}
        for name, stype in table.items():
            if not IDENT.match(name):
                self.add("tenant_settings", f"invalid setting name {name!r}")
            if stype not in SETTING_TYPES:
                self.add(f"tenant_settings.{name}", "type must be list, text or int")
        return dict(table)

    def condition(self, where, rule, fields, settings) -> Condition:
        if not isinstance(rule, dict):
            self.add(where, "must be a table")
            return Condition()
        if "any" in rule:
            if "field" in rule:
                self.add(where, "use either 'any' or 'field', not both")
                return Condition()
            self.keys(where, rule, {"any"})
            parts = rule["any"]
            if not isinstance(parts, list) or not parts:
                self.add(where, "'any' needs at least one condition")
                return Condition()
            return Condition(
                any=tuple(
                    self.condition(f"{where}.any[{i}]", part, fields, settings)
                    for i, part in enumerate(parts)
                )
            )
        name, op = rule.get("field"), rule.get("op")
        if name not in fields:
            self.add(where, f"unknown field '{name}'")
            return Condition()
        if op not in ALL_OPS:
            self.add(where, f"unknown op '{op}'")
            return Condition()
        ftype, choices = fields[name]
        if ftype not in OPS_BY_TYPE:  # the field's bad type is already reported
            return Condition()
        target = name if name in BUILTIN_FIELDS else f"a {ftype} field"
        if op not in OPS_BY_TYPE[ftype]:
            self.add(where, f"'{op}' doesn't work on {target}")
            return Condition()
        for key in rule:
            if key not in {"field", "op"} | OP_ARGS[op]:
                self.add(where, f"unexpected key '{key}'")
        value, values = rule.get("value"), rule.get("values")
        months, setting = rule.get("months"), rule.get("setting")
        if op in ("eq", "ne"):
            if "value" not in rule:
                self.add(where, "needs a 'value'")
            else:
                self.value(where, name, ftype, choices, value)
        if op in ("in", "not_in"):
            if not isinstance(values, list) or not values:
                self.add(where, "needs a non-empty 'values' list")
                values = []
            for v in values:
                self.value(where, name, ftype, choices, v)
        if op in ("gte", "lte") and not _is_int(value):
            self.add(where, "needs a whole number 'value'")
        if op == "within_months" and not (_is_int(months) and 1 <= months <= 120):
            self.add(where, "months must be 1-120")
        if op == "overlaps_setting" and setting not in settings:
            self.add(where, f"setting '{setting}' is not declared in [tenant_settings]")
        return Condition(name, op, value, tuple(values or ()), months, setting)

    def value(self, where, name, ftype, choices, value):
        if ftype == "bool" and not isinstance(value, bool):
            self.add(where, "needs true or false")
        elif ftype == "int" and not _is_int(value):
            self.add(where, "needs a whole number 'value'")
        elif ftype in ("text", "choice") and not _is_text(value):
            self.add(where, "needs non-empty text")
        elif ftype == "choice" and value not in choices:
            self.add(where, f"{value!r} is not a choice of {name}")

    def conditions(self, where, rules, fields, settings) -> tuple:
        if not isinstance(rules, list) or not rules:
            self.add(where, "needs at least one condition")
            return ()
        return tuple(
            self.condition(f"{where}[{i}]", rule, fields, settings) for i, rule in enumerate(rules)
        )

    def scoring(self, table, fields, settings) -> Scoring:
        if not isinstance(table, dict):
            self.add("scoring", "must be a table")
            return Scoring((), (), ())
        self.keys("scoring", table, {"hot", "warm", "flags"})
        for level in ("hot", "warm"):
            if level not in table:
                self.add("scoring", f"missing '{level}'")
        hot = (
            self.conditions("scoring.hot", table.get("hot"), fields, settings)
            if "hot" in table
            else ()
        )
        warm = (
            self.conditions("scoring.warm", table.get("warm"), fields, settings)
            if "warm" in table
            else ()
        )
        flags, seen = [], set()
        for i, flag in enumerate(table.get("flags", [])):
            where = f"scoring.flags[{i}]"
            if not isinstance(flag, dict):
                self.add(where, "must be a table")
                continue
            self.keys(where, flag, {"name", "when"}, ("name", "when"))
            name = flag.get("name", "")
            if not isinstance(name, str) or not IDENT.match(name):
                self.add(where, f"invalid flag name {name!r}")
            elif name in seen:
                self.add("scoring.flags", f"duplicate flag '{name}'")
            seen.add(name)
            when = flag.get("when")
            if not isinstance(when, list) or not when:
                self.add(where, "'when' needs at least one condition")
                continue
            conds = tuple(
                self.condition(f"{where}.when[{j}]", c, fields, settings)
                for j, c in enumerate(when)
            )
            flags.append(Flag(name, conds))
        return Scoring(hot, warm, tuple(flags))

    def prompt(self, name, text):
        where = f"{name}/prompt.md"
        if not text.strip():
            self.add(where, "empty")
            return
        for placeholder in re.findall(r"\{\{([a-z_]+)\}\}", text):
            if placeholder not in PROMPT_PLACEHOLDERS:
                self.add(where, f"unknown placeholder {{{{{placeholder}}}}}")
        leftover = re.sub(r"\{\{[a-z_]+\}\}", "", text)
        if "{{" in leftover or "}}" in leftover:
            self.add(where, "malformed placeholder (use {{name}} with no spaces)")
        if "{{knowledge_markdown}}" not in text:
            self.add(where, "must contain {{knowledge_markdown}}")


def _read(folder: Path, name: str) -> dict:
    missing = [f for f in FILES if not (folder / f).is_file()]
    if missing:
        raise PackError("; ".join(f"{name}/{f}: missing" for f in missing))
    texts = {}
    for f in FILES:
        try:
            texts[f] = (folder / f).read_bytes().decode("utf-8")
        except UnicodeDecodeError as err:
            raise PackError(f"{name}/{f}: not valid UTF-8") from err
    return texts


def load_pack(name: str, packs_dir: Path = PACKS_DIR) -> Pack:
    """Read and validate packs_dir/<name>. Raises PackError listing every problem."""
    if not isinstance(name, str) or not PACK_NAME.match(name):
        raise PackError(f"invalid pack name {name!r}")
    folder = packs_dir / name
    if not folder.is_dir():
        raise PackError(f"pack '{name}' not found in {packs_dir}")
    texts = _read(folder, name)
    try:
        data = tomllib.loads(texts["pack.toml"])
    except tomllib.TOMLDecodeError as err:
        raise PackError(f"{name}/pack.toml: not valid TOML ({err})") from err

    check = _Checker()
    check.keys(
        "pack.toml",
        data,
        {"name", "display_name", "version", "tenant_settings", "stages", "fields", "scoring"},
        ("name", "display_name", "version", "stages", "fields", "scoring"),
    )
    if data.get("name") != name:
        check.add("pack.toml", f"name '{data.get('name')}' doesn't match its folder '{name}'")
    if not _is_text(data.get("display_name")):
        check.add("pack.toml", "display_name must be non-empty text")
    version = data.get("version")
    if not (_is_int(version) and version >= 1):
        check.add("pack.toml", "version must be a whole number ≥ 1")

    stages = check.stages(data.get("stages", {}))
    fields = check.fields(data.get("fields"))
    settings = check.settings(data.get("tenant_settings", {}))
    known = {f.name: (f.type, f.choices) for f in fields}
    known.update({n: (t, ()) for n, t in BUILTIN_FIELDS.items()})
    scoring = check.scoring(data.get("scoring"), known, settings)
    check.prompt(name, texts["prompt.md"])
    if not texts["knowledge_template.md"].strip():
        check.add(f"{name}/knowledge_template.md", "empty")

    if check.problems:
        raise PackError(f"pack '{name}' is invalid:\n  - " + "\n  - ".join(check.problems))
    return Pack(
        name=name,
        display_name=data["display_name"],
        version=version,
        stages=stages,
        fields=fields,
        scoring=scoring,
        tenant_settings=settings,
        prompt=texts["prompt.md"],
        knowledge_template=texts["knowledge_template.md"],
    )
