import dataclasses

import pytest
from cryptography.fernet import Fernet

from app.config import REQUIRED, SECRET_FIELDS, Config, ConfigError, load_config

FERNET = Fernet.generate_key().decode()
SESSION = "s" * 40
DB_URL = "postgresql://bot:hunter2-secret@db.example.com:5432/chatbot"


def valid_env(**overrides):
    env = {
        "ENV": "test",
        "DATABASE_URL": DB_URL,
        "FERNET_KEY": FERNET,
        "SESSION_SECRET": SESSION,
        "PUBLIC_BASE_URL": "https://bot.example.com",
    }
    env.update(overrides)
    return {k: v for k, v in env.items() if v is not None}


def error_for(env):
    with pytest.raises(ConfigError) as exc:
        load_config(env)
    return str(exc.value)


def test_valid_env_loads():
    cfg = load_config(valid_env())
    assert cfg.env == "test"
    assert cfg.database_url == DB_URL
    assert cfg.fernet_key == FERNET
    assert cfg.session_secret == SESSION
    assert cfg.public_base_url == "https://bot.example.com"


@pytest.mark.parametrize("name", REQUIRED)
def test_each_missing_required_var_is_named(name):
    msg = error_for(valid_env(**{name: None}))
    assert name in msg
    assert "missing" in msg


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_blank_value_counts_as_missing(blank):
    assert "SESSION_SECRET: missing" in error_for(valid_env(SESSION_SECRET=blank))


def test_all_problems_reported_together():
    msg = error_for({"ENV": "prod"})
    for name in REQUIRED:
        assert name in msg


def test_error_never_contains_secret_values():
    env = valid_env(ENV="nope", FERNET_KEY="not-a-key-secret123", SESSION_SECRET="short-secret")
    env["DATABASE_URL"] = "mysql://bot:hunter2-secret@host/db"
    msg = error_for(env)
    for secret in ("hunter2-secret", "not-a-key-secret123", "short-secret"):
        assert secret not in msg


def test_surrounding_whitespace_is_stripped():
    cfg = load_config(valid_env(SESSION_SECRET=f"  {SESSION}\n", ENV=" test "))
    assert cfg.session_secret == SESSION
    assert cfg.env == "test"


@pytest.mark.parametrize("env_value", ["prod", "dev", "Production", "TEST", "local"])
def test_env_must_be_known(env_value):
    assert "ENV: must be one of" in error_for(valid_env(ENV=env_value))


@pytest.mark.parametrize("env_value", ["test", "staging", "production"])
def test_known_envs_accepted(env_value):
    assert load_config(valid_env(ENV=env_value)).env == env_value


@pytest.mark.parametrize(
    "bad_key",
    [
        "not-a-key",
        "a" * 44,  # right length, wrong content after base64 decoding
        pytest.param(Fernet.generate_key().decode()[:-2], id="truncated"),
    ],
)
def test_invalid_fernet_key_fails_at_load(bad_key):
    assert "FERNET_KEY: not a valid Fernet key" in error_for(valid_env(FERNET_KEY=bad_key))


def test_session_secret_minimum_length():
    assert "SESSION_SECRET: must be at least 32 characters" in error_for(
        valid_env(SESSION_SECRET="x" * 31)
    )
    assert load_config(valid_env(SESSION_SECRET="x" * 32)).session_secret == "x" * 32


@pytest.mark.parametrize(
    "url",
    [
        "not a url",
        "mysql://u:p@host/db",
        "postgresql://u:p@/db",  # no host
        "postgresql://u:p@host",  # no database name
        "postgresql://u:p@host/",  # empty database name
        "postgresql://u:p@host:notaport/db",  # port not a number
        "postgresql://u:p@host:99999/db",  # port out of range
        "//u:p@host/db",  # no scheme
    ],
)
def test_malformed_database_url(url):
    assert "DATABASE_URL: must look like postgresql://" in error_for(valid_env(DATABASE_URL=url))


@pytest.mark.parametrize(
    "url",
    [
        "postgres://u:p@host/db",
        "postgresql://u:p@host:5432/db?sslmode=require",
        "postgresql://u@localhost/db",
    ],
)
def test_valid_database_urls(url):
    assert load_config(valid_env(DATABASE_URL=url)).database_url == url


def test_public_base_url_http_rejected_in_production():
    msg = error_for(valid_env(ENV="production", PUBLIC_BASE_URL="http://bot.example.com"))
    assert "PUBLIC_BASE_URL: must use https in production" in msg


@pytest.mark.parametrize("env_value", ["test", "staging"])
def test_public_base_url_http_allowed_outside_production(env_value):
    cfg = load_config(valid_env(ENV=env_value, PUBLIC_BASE_URL="http://localhost:8000"))
    assert cfg.public_base_url == "http://localhost:8000"


@pytest.mark.parametrize(
    "url", ["bot.example.com", "ftp://bot.example.com", "https://", "https:///path"]
)
def test_public_base_url_must_be_absolute_http_url(url):
    assert "PUBLIC_BASE_URL: must be an absolute http(s) URL" in error_for(
        valid_env(PUBLIC_BASE_URL=url)
    )


def test_public_base_url_uppercase_https_accepted_in_production():
    cfg = load_config(valid_env(ENV="production", PUBLIC_BASE_URL="HTTPS://Bot.Example.com"))
    assert cfg.public_base_url == "HTTPS://Bot.Example.com"


def test_missing_env_with_http_url_reports_only_missing_env():
    msg = error_for(valid_env(ENV=None, PUBLIC_BASE_URL="http://bot.example.com"))
    assert "ENV: missing" in msg
    assert "PUBLIC_BASE_URL" not in msg


def test_ipv6_database_host_accepted():
    url = "postgresql://u:p@[::1]:5432/db"
    assert load_config(valid_env(DATABASE_URL=url)).database_url == url


def test_public_base_url_trailing_slash_removed():
    cfg = load_config(valid_env(PUBLIC_BASE_URL="https://bot.example.com/"))
    assert cfg.public_base_url == "https://bot.example.com"


def test_config_is_immutable():
    cfg = load_config(valid_env())
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.env = "production"


def test_repr_masks_every_secret():
    cfg = load_config(valid_env())
    text = repr(cfg)
    assert FERNET not in text
    assert SESSION not in text
    assert "hunter2-secret" not in text
    for field in SECRET_FIELDS:
        assert f"{field}='***'" in text
    assert "env='test'" in text
    assert "public_base_url='https://bot.example.com'" in text
    assert str(cfg) == text


def test_secret_fields_are_real_fields():
    names = {f.name for f in dataclasses.fields(Config)}
    assert set(SECRET_FIELDS) <= names


def test_load_config_reads_os_environ_by_default(monkeypatch):
    for key, value in valid_env(ENV="staging").items():
        monkeypatch.setenv(key, value)
    assert load_config().env == "staging"
