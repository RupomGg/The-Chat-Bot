"""Settings loaded from environment variables once, at startup.

Only variables that existing code uses are defined here; later portions add theirs.
Error messages name the variable and the rule, never the value (values may be secrets).
"""

import dataclasses
import os
from collections.abc import Mapping
from urllib.parse import urlsplit

from cryptography.fernet import Fernet

ENVS = ("test", "staging", "production")
REQUIRED = ("ENV", "DATABASE_URL", "FERNET_KEY", "SESSION_SECRET", "PUBLIC_BASE_URL")
SECRET_FIELDS = (
    "database_url",
    "fernet_key",
    "session_secret",
    "anthropic_api_key",
    "gemini_api_key",
)
MIN_SESSION_SECRET = 32


class ConfigError(Exception):
    """Raised at startup when settings are missing or invalid."""


@dataclasses.dataclass(frozen=True)
class Config:
    env: str
    database_url: str
    fernet_key: str
    session_secret: str
    public_base_url: str
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    def __repr__(self) -> str:
        parts = []
        for field in dataclasses.fields(self):
            value = "***" if field.name in SECRET_FIELDS else getattr(self, field.name)
            parts.append(f"{field.name}={value!r}")
        return f"Config({', '.join(parts)})"

    __str__ = __repr__


def _valid_database_url(url: str) -> bool:
    parts = urlsplit(url)
    try:
        parts.port  # noqa: B018 - raises ValueError for a non-numeric or out-of-range port
    except ValueError:
        return False
    return (
        parts.scheme in ("postgresql", "postgres")
        and bool(parts.hostname)
        and parts.path.strip("/") != ""
    )


def _valid_fernet_key(key: str) -> bool:
    try:
        Fernet(key)
    except ValueError:
        return False
    return True


def load_config(environ: Mapping[str, str] | None = None) -> Config:
    """Read and validate settings. Reports every problem at once."""
    source = os.environ if environ is None else environ
    values = {name: source.get(name, "").strip() for name in REQUIRED}
    problems = [f"{name}: missing" for name, value in values.items() if not value]

    env = values["ENV"]
    if env and env not in ENVS:
        problems.append(f"ENV: must be one of {', '.join(ENVS)}")

    if values["DATABASE_URL"] and not _valid_database_url(values["DATABASE_URL"]):
        problems.append("DATABASE_URL: must look like postgresql://user:password@host:port/dbname")

    if values["FERNET_KEY"] and not _valid_fernet_key(values["FERNET_KEY"]):
        problems.append("FERNET_KEY: not a valid Fernet key (generate with Fernet.generate_key())")

    secret = values["SESSION_SECRET"]
    if secret and len(secret) < MIN_SESSION_SECRET:
        problems.append(f"SESSION_SECRET: must be at least {MIN_SESSION_SECRET} characters")

    base_url = values["PUBLIC_BASE_URL"].rstrip("/")
    if base_url:
        parts = urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            problems.append("PUBLIC_BASE_URL: must be an absolute http(s) URL")
        elif env == "production" and parts.scheme != "https":
            problems.append("PUBLIC_BASE_URL: must use https in production")

    if problems:
        raise ConfigError("Invalid configuration:\n  " + "\n  ".join(problems))

    return Config(
        env=env,
        database_url=values["DATABASE_URL"],
        fernet_key=values["FERNET_KEY"],
        session_secret=secret,
        public_base_url=base_url,
        anthropic_api_key=source.get("ANTHROPIC_API_KEY", "").strip(),
        gemini_api_key=source.get("GEMINI_API_KEY", "").strip(),
    )
