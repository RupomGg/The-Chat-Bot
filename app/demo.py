"""The demo company (P4.5): made-up sample data for trying the bot, never a real business.

`seed()` creates it, or brings it up to date; running it again never duplicates anything.
"""

import pathlib

from psycopg.types.json import Jsonb

from app.knowledge import normalize_knowledge, publish_version, published_knowledge, save_version
from app.quick_answers import save_quick_answer

ROOT = pathlib.Path(__file__).resolve().parent.parent
KNOWLEDGE_FILE = ROOT / "tenants" / "demo" / "knowledge.md"
SLUG = "demo"
NAME = "Demo Consultancy"
FALLBACK = "Thanks! A counsellor will reply here soon. / ধন্যবাদ! একজন কাউন্সেলর শীঘ্রই এখানে উত্তর দেবেন।"
SETTINGS = {"served_countries": ["UK", "Malaysia", "Canada"]}
OPEN_DAYS = (1, 2, 3, 4, 6, 7)  # ISO weekdays: Friday (5) closed
BRANCHES = (  # name, opens, closes, slot minutes, seats per slot
    ("Banani", "10:00", "19:00", 60, 2),
    ("Online", "11:00", "20:00", 60, 1),
)
QUICK_ANSWERS = (
    {
        "code": "FEES",
        "triggers": ["fees", "service charge", "apnader fee koto", "খরচ কত"],
        "answers": {
            "en": "Counselling is free. Application processing is 5,000 taka per university, "
            "or 15,000 taka for up to 4.",
            "bn": "আমাদের কাউন্সেলিং সম্পূর্ণ ফ্রি। আবেদন প্রসেসিং প্রতি বিশ্ববিদ্যালয় ৫,০০০ টাকা, "
            "অথবা ৪টি পর্যন্ত ১৫,০০০ টাকা।",
        },
    },
    {
        "code": "OFFICE",
        "triggers": ["address", "office kothay", "ঠিকানা", "location"],
        "answers": {
            "en": "House 5, Road 11, Banani, Dhaka. Open Saturday to Thursday, 10:00-19:00.",
            "bn": "বাড়ি ৫, রোড ১১, বনানী, ঢাকা। শনি থেকে বৃহস্পতি, সকাল ১০টা থেকে সন্ধ্যা ৭টা।",
        },
    },
    {"code": "BOOK", "triggers": ["book", "appointment"], "action": "start_booking"},
)


def _one(conn, query, params=()):
    row = conn.execute(query, params).fetchone()
    return None if row is None else row[0]


def seed(conn, *, model: str = "claude-haiku-4-5") -> dict:
    """Create or update the demo company. Safe to run any number of times."""
    with conn.transaction():
        tenant = _one(
            conn,
            "INSERT INTO tenants (slug, name, fallback_text, industry, settings, model)"
            " VALUES (%s, %s, %s, 'study_abroad', %s, %s)"
            " ON CONFLICT (slug) DO UPDATE SET model = EXCLUDED.model RETURNING id",
            (SLUG, NAME, FALLBACK, Jsonb(SETTINGS), model),
        )
        channel = _one(
            conn, "SELECT id FROM channels WHERE tenant_id = %s AND type = 'web'", (tenant,)
        ) or _one(
            conn,
            "INSERT INTO channels (tenant_id, type) VALUES (%s, 'web') RETURNING id",
            (tenant,),
        )
        for name, opens, closes, minutes, seats in BRANCHES:
            branch = _one(
                conn, "SELECT id FROM branches WHERE tenant_id = %s AND name = %s", (tenant, name)
            )
            if branch is None:
                branch = _one(
                    conn,
                    "INSERT INTO branches (tenant_id, name) VALUES (%s, %s) RETURNING id",
                    (tenant, name),
                )
                for day in OPEN_DAYS:
                    conn.execute(
                        "INSERT INTO schedules (tenant_id, branch_id, weekday, start_time,"
                        " end_time, slot_minutes, capacity) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (tenant, branch, day, opens, closes, minutes, seats),
                    )
        for answer in QUICK_ANSWERS:
            exists = _one(
                conn,
                "SELECT id FROM quick_answers WHERE tenant_id = %s AND code = %s",
                (tenant, answer["code"]),
            )
            if exists is None:
                save_quick_answer(conn, tenant, **answer)
        content = normalize_knowledge(KNOWLEDGE_FILE.read_text(encoding="utf-8"))
        if published_knowledge(conn, tenant) != content:
            version = save_version(conn, tenant, content, created_by="demo seed")
            # Demo only: real companies pass the eval suite first (P7.1).
            conn.execute(
                "UPDATE knowledge_versions SET eval_passed = true WHERE id = %s", (version,)
            )
            publish_version(conn, tenant, version)
    return {"tenant": tenant, "channel": channel}
