"""Chat with the demo company in the terminal (P4.5).

    python -m app.chat            fake AI: no key, no cost, nothing leaves this computer
    python -m app.chat --gemini   real Gemini (GEMINI_API_KEY); free tier: made-up data only
    python -m app.chat --claude   real Claude (ANTHROPIC_API_KEY)

Type a message and press Enter. Commands: /tap CODE (press a button), /new (become a new
customer), /quit. Ctrl+C also quits cleanly.
"""

import argparse
import datetime
import os
import pathlib
import uuid
from types import SimpleNamespace

import psycopg

from app import db, llm
from app.demo import seed
from app.engine import Engine, Inbound

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODELS = {"fake": "claude-haiku-4-5", "claude": "claude-haiku-4-5", "gemini": "gemini-3.5-flash"}
KEYS = {"claude": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}


class FakeAI:
    """Stands in for the AI: repeats the question, so the flow can be tried without a key."""

    def __init__(self):
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **request):
        last = request["messages"][-1]["content"]
        question = last.split(chr(10), 1)[-1] if isinstance(last, str) else "..."
        text = f"(fake AI, no real answer) You asked: {question[:80]}"
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )


def setting(name: str) -> str | None:
    """From the environment, else from the project's .env file."""
    if os.environ.get(name):
        return os.environ[name]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name and value.strip():
                return value.strip()
    return None


def _clients(provider: str) -> dict:
    if provider == "fake":
        return {"claude": FakeAI()}
    if provider == "gemini":
        return {"gemini": llm.make_gemini_client(setting(KEYS["gemini"]))}
    return {"claude": llm.make_client(setting(KEYS["claude"]))}


def main(argv=None, *, read=input, write=print, clock=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.chat", description=__doc__)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--fake", dest="provider", action="store_const", const="fake")
    choice.add_argument("--gemini", dest="provider", action="store_const", const="gemini")
    choice.add_argument("--claude", dest="provider", action="store_const", const="claude")
    parser.set_defaults(provider="fake")
    args = parser.parse_args(argv)
    clock = clock or (lambda: datetime.datetime.now(datetime.UTC))

    url = setting("DATABASE_URL")
    if not url:
        write("DATABASE_URL is not set (see .env.example).")
        return 2
    if args.provider in KEYS and not setting(KEYS[args.provider]):
        write(f"{KEYS[args.provider]} is not set. Set it in this terminal first, or use --fake.")
        return 2

    try:
        db.wait_for_db(url, attempts=1)  # one try: a person is waiting at the keyboard
    except db.DatabaseUnavailable as error:
        write(f"Can't reach the database ({error}). Check DATABASE_URL in .env.")
        return 2
    except psycopg.ProgrammingError:  # not an address at all, e.g. "DATABASE_URL=" twice
        write("DATABASE_URL in .env isn't a valid address; it should look like")
        write("DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/DATABASE")
        return 2
    db.migrate(url)
    with psycopg.connect(url, autocommit=True) as conn:
        ids = seed(conn, model=MODELS[args.provider])
        engine = Engine(_clients(args.provider), notify=lambda kind, detail: write(f"  [{kind}]"))
        user = "cli-" + uuid.uuid4().hex[:8]
        write(f"Demo Consultancy, {args.provider} AI. /tap CODE, /new, /quit")
        while True:
            try:
                line = read("you> ").strip()
                if not line:
                    continue
                if line == "/quit":
                    break
                if line == "/new":
                    user = "cli-" + uuid.uuid4().hex[:8]
                    write("  (you are now a new customer)")
                    continue
                now = clock()
                tapped = line[5:].strip().upper() if line.startswith("/tap ") else None
                msg = Inbound(
                    ids["tenant"],
                    ids["channel"],
                    user,
                    now,
                    text=None if tapped else line,
                    payload=tapped,
                )
                reply = engine.handle(conn, msg, now=now)
            except (EOFError, KeyboardInterrupt):
                break
            if reply.text is None:
                write("  (the bot stays quiet: a person has taken over this chat)")
                continue
            write(f"bot> {reply.text}")
            extra = f"  [{reply.source}]"
            if reply.buttons:
                extra += f" buttons: {', '.join(reply.buttons)}"
            write(extra)
    write("bye")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
