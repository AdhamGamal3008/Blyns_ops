"""Env-driven settings (docs/ARCHITECTURE.md §1).

No literal connection strings anywhere else in the codebase. Load precedence:
real environment variables > .env file > defaults here. `env` drives the
behavior differences described in docs/ENVIRONMENTS.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor the .env to the backend root (this file is backend/app/core/config.py)
# so config loads no matter which directory the process is launched from. In
# production the file is absent and pydantic-settings ignores it — config comes
# from injected env vars (docs/ENVIRONMENTS.md §4).
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    env: Literal["local", "test", "production"] = "local"

    # Mongo
    mongo_uri: str = "mongodb://localhost:27017"
    control_db_name: str = "erp_control"
    tenant_db_prefix: str = "erp_tenant_"

    # Auth — jwt_secret has no default: it must come from the environment/.env
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 30
    refresh_token_ttl_days: int = 14
    admin_token_audience: str = "erp-admin"
    client_token_audience: str = "erp-client"

    # Security defaults (overridable per company)
    default_failed_login_threshold: int = 5
    default_lockout_minutes: int = 15

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_window_sec: int = 60
    rate_limit_max_requests: int = 120

    # Project document uploads (docs/modules/PROJECT_MANAGEMENT.md §3.7): files
    # are stored self-hosted in the tenant DB via GridFS; this caps a single upload.
    max_upload_mb: int = 25

    # CSV import (docs/modules/CRM.md §7). A separate, much smaller cap than
    # `max_upload_mb`: an import is parsed into memory row by row, so the row
    # count is the real limit and the byte cap is the cheap first guard.
    max_import_mb: int = 5
    max_import_rows: int = 5000

    # Quick-action ranking (docs/QUICK_ACTIONS_PERSONALIZATION_PLAN.md). Pure,
    # in-house scoring over the caller's OWN recent activity_log — no external
    # service, deterministic. All env-overridable (ERP_QA_*) and valid across
    # local/test/prod. `window_days` bounds the fetch; `half_life_days` sets the
    # recency decay; the weights trade off exact-action vs module engagement;
    # `event_fetch_cap` bounds cost.
    qa_window_days: int = 30
    qa_half_life_days: float = 7.0
    qa_weight_exact: float = 3.0
    qa_weight_module: float = 1.0
    qa_role_weight_write: float = 2.0
    qa_role_weight_read: float = 0.5
    qa_tie_epsilon: float = 0.001
    qa_event_fetch_cap: int = 500

    # CORS — exact frontend origin(s)
    cors_origins: list[str] = ["http://localhost:5173"]

    # Platform metrics collector (docs/ADMIN_PORTAL.md §4): in-process loop
    # writing dbStats/activity snapshots. 0 disables (tests).
    metrics_interval_sec: int = 300

    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_prefix="ERP_")

    @property
    def docs_enabled(self) -> bool:
        """/docs is on for local + test, off for production (ENVIRONMENTS.md §1)."""
        return self.env != "production"

    def production_problems(self) -> list[str]:
        """Config that must never ship to production (docs/ENVIRONMENTS.md §4/§6).

        Returns a human-readable list of violations; empty means safe. Enforced
        at startup by `validate_for_production` so a misconfigured production
        process fails fast instead of serving with a dev secret or open docs.
        """
        problems: list[str] = []

        weak_secrets = {"", "change-me", "change-me-dev-only", "dev", "secret", "test"}
        if self.jwt_secret in weak_secrets or len(self.jwt_secret) < 32:
            problems.append(
                "ERP_JWT_SECRET is empty, a known dev value, or shorter than 32 "
                "chars — inject a strong secret (e.g. `openssl rand -hex 32`)."
            )

        if self.docs_enabled:
            problems.append("/docs must be disabled in production.")

        if not self.cors_origins:
            problems.append("ERP_CORS_ORIGINS must list the exact frontend origin(s).")
        localhost = [o for o in self.cors_origins if "localhost" in o or "127.0.0.1" in o]
        if localhost:
            problems.append(
                f"CORS origins point at localhost in production: {localhost}."
            )

        if "localhost" in self.mongo_uri or "127.0.0.1" in self.mongo_uri:
            problems.append(
                "ERP_MONGO_URI points at localhost — production Mongo is an "
                "injected replica-set secret (docs/ENVIRONMENTS.md §4)."
            )

        return problems


def validate_for_production(cfg: Settings) -> None:
    """Fail fast at startup if a production process carries unsafe config.

    No-op outside production. Raises RuntimeError listing every violation so the
    operator sees all of them at once rather than one redeploy at a time.
    """
    if cfg.env != "production":
        return
    problems = cfg.production_problems()
    if problems:
        raise RuntimeError(
            "Refusing to start in production with unsafe configuration:\n  - "
            + "\n  - ".join(problems)
        )


# jwt_secret arrives via env/.env at runtime (pydantic-settings); mypy can't see that.
settings = Settings()  # type: ignore[call-arg]  # imported everywhere
