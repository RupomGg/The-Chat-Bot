# Admissions Assistant

AI admissions assistant for study-abroad consultancies (Messenger, WhatsApp, Telegram, web).
What to build: `PRD.md` · Build order and quality gate: `INSTRUCTION.md` · Change log: `DECISION.md`.

## Setup (Windows, Python 3.13)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
cp .env.example .env    # then fill in FERNET_KEY and SESSION_SECRET (commands inside)
```

## Run

```bash
.venv/Scripts/python -m uvicorn --factory app.main:create_app --env-file .env
```

Open http://localhost:8000/healthz, which should return `{"status":"ok"}`.

## Test (the gate, INSTRUCTION.md §2)

```bash
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m coverage run -m pytest -q
.venv/Scripts/python -m coverage report --fail-under=100
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
```
