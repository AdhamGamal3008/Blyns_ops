"""Env-driven settings (docs/ARCHITECTURE.md §1).

No literal connection strings anywhere else in the codebase. Load precedence:
real environment variables > .env file > defaults here. `env` drives the
behavior differences described in docs/ENVIRONMENTS.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # CORS — exact frontend origin(s)
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ERP_")

    @property
    def docs_enabled(self) -> bool:
        """/docs is on for local + test, off for production (ENVIRONMENTS.md §1)."""
        return self.env != "production"


# jwt_secret arrives via env/.env at runtime (pydantic-settings); mypy can't see that.
settings = Settings()  # type: ignore[call-arg]  # imported everywhere
