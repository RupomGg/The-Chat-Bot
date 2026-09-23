"""FastAPI application factory.

Run locally with:  uvicorn --factory app.main:create_app --env-file .env
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import db
from app.config import Config, load_config


def create_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()  # fail at startup, not at first request

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db.wait_for_db(config.database_url)
        db.migrate(config.database_url)
        app.state.pool = db.open_pool(config.database_url)
        try:
            yield
        finally:
            app.state.pool.close()

    docs = config.env != "production"
    app = FastAPI(
        title="Admissions Assistant",
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
        lifespan=lifespan,
    )
    app.state.config = config

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
