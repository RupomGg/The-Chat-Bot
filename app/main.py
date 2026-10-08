"""FastAPI application factory.

Run locally with:  uvicorn --factory app.main:create_app --env-file .env
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import db, jobs, llm
from app.channels import messenger, web
from app.config import Config, load_config
from app.engine import Engine


def ai_clients(config: Config) -> dict:
    """Only the AIs that have a key; a company whose model has no key can't get AI replies."""
    clients = {}
    if config.anthropic_api_key:
        clients["claude"] = llm.make_client(config.anthropic_api_key)
    if config.gemini_api_key:
        clients["gemini"] = llm.make_gemini_client(config.gemini_api_key)
    return clients


def create_app(config: Config | None = None, engine: Engine | None = None) -> FastAPI:
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
    app.state.engine = engine or Engine(ai_clients(config))
    app.state.per_visitor = web.RateLimit(web.PER_VISITOR)
    app.state.per_ip = web.RateLimit(web.PER_IP)
    app.include_router(web.router)
    app.include_router(messenger.router)

    @app.get("/healthz")
    def healthz() -> dict:
        with app.state.pool.connection() as conn:
            return {"status": "ok", "queue": jobs.queue_stats(conn)}

    return app
