"""FastAPI app factory + router mounting (docs/ARCHITECTURE.md, ENVIRONMENTS.md).

Behavior differences between local / test / production are driven ONLY by
Settings (env vars): docs on/off, CORS origins, rate limiting. Module routers
are mounted here as each build phase lands.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.db import close_db_manager, get_db_manager, init_db_manager
from app.core.errors import register_exception_handlers
from app.core.rate_limit import RateLimitMiddleware
from app.shared.schemas import envelope

try:
    APP_VERSION = version("erp-backend")
except PackageNotFoundError:  # running from a raw checkout
    APP_VERSION = "0.0.0-dev"


def create_app(cfg: Settings | None = None) -> FastAPI:
    cfg = cfg or default_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = init_db_manager(cfg.mongo_uri)
        app.state.db = db
        yield
        close_db_manager()

    app = FastAPI(
        title="ERP",
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if cfg.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if cfg.docs_enabled else None,
    )

    register_exception_handlers(app)

    # Order matters: rate limiting wraps everything, CORS inside it.
    app.add_middleware(CORSMiddleware,
                       allow_origins=cfg.cors_origins,
                       allow_credentials=True,
                       allow_methods=["*"],
                       allow_headers=["*"])
    app.add_middleware(RateLimitMiddleware, cfg=cfg)

    @app.get("/health")
    async def health():
        try:
            mongo_ok = await get_db_manager().ping()
        except Exception:
            mongo_ok = False
        body = envelope(
            {
                "status": "ok" if mongo_ok else "degraded",
                "mongo": mongo_ok,
                "env": cfg.env,
                "version": APP_VERSION,
            }
        )
        if not mongo_ok:
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=503, content=body)
        return body

    # --- module routers mount here as phases land ---
    # Phase 2: control_plane provisioning/companies
    # Phase 3: auth (admin + client realms)
    # Phase 4+: admin portal, dashboard, settings, crm, inventory, finance, projects

    return app


app = create_app()
