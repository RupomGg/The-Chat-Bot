import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import load_config
from app.main import create_app


@pytest.fixture
def env_vars():
    return {
        "ENV": "test",
        "DATABASE_URL": "postgresql://bot:pw@localhost:5432/chatbot",
        "FERNET_KEY": Fernet.generate_key().decode(),
        "SESSION_SECRET": "t" * 40,
        "PUBLIC_BASE_URL": "https://bot.example.com",
    }


@pytest.fixture
def config(env_vars):
    return load_config(env_vars)


@pytest.fixture
def client(config):
    with TestClient(create_app(config)) as c:
        yield c
