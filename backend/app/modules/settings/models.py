"""Settings module payloads (docs/modules/SETTINGS.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.shared.validation import EMAIL_PATTERN


class CompanyProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    legal_name: str | None = None
    logo_ref: str | None = None
    timezone: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    fiscal_year_start: str | None = Field(
        default=None, pattern=r"^\d{2}-\d{2}$"
    )
    contact: dict | None = None
    # INVENTORY.md §2: negative stock is rejected by default; this is the
    # "company setting [that] may allow it".
    allow_negative_stock: bool | None = None

    @field_validator("logo_ref")
    @classmethod
    def _valid_logo(cls, v: str | None) -> str | None:
        # The logo is uploaded as an inline data URI (kept small); a plain URL is
        # also allowed. Guard the data-URI form: image only, ~256 KB cap.
        if v and v.startswith("data:"):
            if not v.startswith("data:image/"):
                raise ValueError("logo must be an image")
            if len(v) > 360_000:  # ~256 KB encoded as base64
                raise ValueError("logo is too large (max ~256 KB)")
        return v


class EmployeeCreate(BaseModel):
    name: str = Field(min_length=1)
    email: str
    role_id: str

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        if not EMAIL_PATTERN.match(v):
            raise ValueError("invalid email address")
        return v.lower()


class EmployeePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    role_id: str | None = None


class EmployeeBlockBody(BaseModel):
    blocked: bool


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    permissions: dict[str, int]
    # Per-tab CSV grants: {export: [...], import: [...], approve_import: [...]}
    # of "{module}:{entity}" keys. Validated in the service (csv_access.validate),
    # like `permissions`. Omit → no CSV access.
    csv_access: dict[str, list[str]] | None = None


class RolePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    permissions: dict[str, int] | None = None
    csv_access: dict[str, list[str]] | None = None


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1)
    start: datetime
    end: datetime | None = None
    all_day: bool = True
    visibility: Literal["company", "role", "owner"] = "company"
    role_id: str | None = None  # required target when visibility="role"


class CalendarEventPatch(BaseModel):
    title: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    all_day: bool | None = None
    visibility: Literal["company", "role", "owner"] | None = None
    role_id: str | None = None


class ApproverMapPatch(BaseModel):
    """Edit one approver-role mapping (PROJECT_MANAGEMENT.md §9): resolve a
    position to tenant client roles and/or specific users."""

    client_roles: list[str] | None = None
    assigned_user_ids: list[str] | None = None
