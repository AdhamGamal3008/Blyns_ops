"""Company registry models (docs/MULTITENANCY.md §2, docs/ADMIN_PORTAL.md §1)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

CompanyStatus = Literal["active", "blocked", "suspended", "provisioning", "failed"]

SLUG_PATTERN = re.compile(r"^[a-z0-9-]{3,40}$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Modules a tenant may enable, in seeding order (docs/MULTITENANCY.md §5).
KNOWN_MODULES = ["dashboard", "settings", "projects", "crm", "inventory", "finance"]


class OwnerPayload(BaseModel):
    name: str = Field(min_length=1)
    email: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        if not _EMAIL_PATTERN.match(v):
            raise ValueError("invalid email address")
        return v.lower()


class SecurityPolicy(BaseModel):
    """Per-company overrides of the global failed-login defaults."""

    failed_login_threshold: int = Field(
        default_factory=lambda: settings.default_failed_login_threshold, ge=1
    )
    lockout_minutes: int = Field(
        default_factory=lambda: settings.default_lockout_minutes, ge=1
    )


class OnboardCompanyPayload(BaseModel):
    """The admin "onboard company" request body (docs/ADMIN_PORTAL.md §1)."""

    name: str = Field(min_length=1)
    slug: str
    seat_limit: int = Field(default=25, ge=1)
    enabled_modules: list[str] = Field(default_factory=lambda: list(KNOWN_MODULES))
    owner: OwnerPayload
    security: SecurityPolicy = Field(default_factory=SecurityPolicy)

    @field_validator("slug")
    @classmethod
    def _valid_slug(cls, v: str) -> str:
        if not SLUG_PATTERN.match(v):
            raise ValueError("slug must match ^[a-z0-9-]{3,40}$")
        return v

    @field_validator("enabled_modules")
    @classmethod
    def _known_modules(cls, v: list[str]) -> list[str]:
        unknown = set(v) - set(KNOWN_MODULES)
        if unknown:
            raise ValueError(f"unknown modules: {sorted(unknown)}")
        # de-dupe, preserve canonical seeding order
        return [m for m in KNOWN_MODULES if m in v]

    @property
    def db_name(self) -> str:
        return f"{settings.tenant_db_prefix}{self.slug}"
