import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError
from app.main import create_app


def test_healthz_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_never_leaks_secrets(client, config):
    body = client.get("/healthz").text
    for secret in (config.fernet_key, config.session_secret, config.database_url):
        assert secret not in body


def test_healthz_rejects_post(client):
    assert client.post("/healthz").status_code == 405


def test_unknown_route_is_404(client):
    assert client.get("/nope").status_code == 404


def test_create_app_fails_at_startup_on_bad_config(monkeypatch):
    monkeypatch.delenv("FERNET_KEY", raising=False)
    monkeypatch.setenv("ENV", "test")
    with pytest.raises(ConfigError, match="FERNET_KEY"):
        create_app()


def test_create_app_loads_environment_when_no_config_given(monkeypatch, env_vars):
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    app = create_app()
    assert app.state.config.env == "test"
    with TestClient(app) as c:
        assert c.get("/healthz").status_code == 200


def test_startup_runs_migrations_and_opens_pool(config):
    app = create_app(config)
    with TestClient(app):
        with app.state.pool.connection() as conn:
            names = conn.execute("SELECT name FROM schema_version ORDER BY version").fetchall()
        assert names == [("000_schema_version.sql",), ("001_init.sql",)]
    assert app.state.pool.closed  # shutdown closes the pool


def test_startup_fails_when_database_unreachable(config, monkeypatch):
    from app import db

    def unreachable(url):
        raise db.DatabaseUnavailable("database unreachable after 6 attempts: refused")

    monkeypatch.setattr(db, "wait_for_db", unreachable)
    with pytest.raises(db.DatabaseUnavailable), TestClient(create_app(config)):
        pass  # never reached: startup fails


def test_api_docs_enabled_outside_production(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_api_docs_disabled_in_production(env_vars):
    from app.config import load_config

    cfg = load_config({**env_vars, "ENV": "production"})
    with TestClient(create_app(cfg)) as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/openapi.json").status_code == 404
