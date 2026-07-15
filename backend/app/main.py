"""FastAPI app factory + router mounting (docs/ARCHITECTURE.md, ENVIRONMENTS.md).

Behavior differences between local / test / production are driven ONLY by
Settings (env vars): docs on/off, CORS origins, rate limiting. Module routers
are mounted here as each build phase lands.
"""

from __future__ import annotations

import asyncio
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

        # In-process metrics collector loop (docs/ADMIN_PORTAL.md §4 perf
        # note): rolling snapshots so the dashboard never fans out live.
        collector_task: asyncio.Task | None = None
        if cfg.metrics_interval_sec > 0:
            from app.control_plane.metrics.collector import collect_platform_metrics

            async def _collect_loop() -> None:
                while True:
                    await asyncio.sleep(cfg.metrics_interval_sec)
                    try:
                        await collect_platform_metrics(db)
                    except Exception:  # collector must never kill the app
                        pass

            collector_task = asyncio.create_task(_collect_loop())

        yield

        if collector_task is not None:
            collector_task.cancel()
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

    # --- module routers (mounted as phases land) ---
    from app.auth.admin_auth import router as admin_auth_router
    from app.auth.client_auth import router as client_auth_router
    from app.control_plane.admin_users.router import router as admin_users_router
    from app.control_plane.companies.router import router as companies_router
    from app.control_plane.metrics.router import router as metrics_router

    app.include_router(admin_auth_router)
    app.include_router(client_auth_router)
    app.include_router(companies_router)
    app.include_router(admin_users_router)
    app.include_router(metrics_router)
    # Phase 5+: client modules (dashboard, settings, crm, inventory, finance, projects)

    return app


app = create_app()
