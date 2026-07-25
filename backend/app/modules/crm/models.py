"""CRM module payloads (docs/modules/CRM.md §1)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.shared.validation import EMAIL_PATTERN

AccountStatus = Literal["prospect", "customer", "inactive"]
LeadStatus = Literal["new", "contacted", "qualified", "unqualified", "converted"]
DealStage = Literal["new", "qualified", "proposal", "negotiation", "won", "lost"]
ActivityType = Literal["call", "email", "meeting", "note", "task"]
EntityType = Literal["account", "contact", "lead", "deal"]


def _optional_email(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    if not EMAIL_PATTERN.match(v):
        raise ValueError("invalid email address")
    return v.lower()


# --- accounts ----------------------------------------------------------------

class AccountCreate(BaseModel):
    name: str = Field(min_length=1)
    industry: str | None = None
    website: str | None = None
    phone: str | None = None
    address: dict | None = None
    status: AccountStatus = "prospect"
    tags: list[str] = Field(default_factory=list)
    owner_id: str | None = None  # defaults to the caller


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    industry: str | None = None
    website: str | None = None
    phone: str | None = None
    address: dict | None = None
    status: AccountStatus | None = None
    tags: list[str] | None = None
    owner_id: str | None = None


# --- contacts ----------------------------------------------------------------

class ContactCreate(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    account_id: str | None = None
    email: str | None = None
    phone: str | None = None
    title: str | None = None
    tags: list[str] = Field(default_factory=list)
    owner_id: str | None = None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str | None) -> str | None:
        return _optional_email(v)


class ContactPatch(BaseModel):
    first_name: str | None = Field(default=None, min_length=1)
    last_name: str | None = Field(default=None, min_length=1)
    account_id: str | None = None
    email: str | None = None
    phone: str | None = None
    title: str | None = None
    tags: list[str] | None = None
    owner_id: str | None = None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str | None) -> str | None:
        return _optional_email(v)


# --- leads -------------------------------------------------------------------

class LeadCreate(BaseModel):
    name: str = Field(min_length=1)
    email: str | None = None
    phone: str | None = None
    source: str | None = None
    status: LeadStatus = "new"
    owner_id: str | None = None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str | None) -> str | None:
        return _optional_email(v)


class LeadPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    email: str | None = None
    phone: str | None = None
    source: str | None = None
    status: LeadStatus | None = None
    owner_id: str | None = None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str | None) -> str | None:
        return _optional_email(v)


class LeadConvert(BaseModel):
    """Convert a lead into account + contact + deal (§2).

    Supply an existing `account_id` to link instead of creating one; omit
    `deal_title` to derive it from the lead name.
    """

    account_id: str | None = None
    account_name: str | None = None
    deal_title: str | None = None
    amount: float = Field(default=0, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    expected_close_date: datetime | None = None


# --- deals -------------------------------------------------------------------

class DealCreate(BaseModel):
    title: str = Field(min_length=1)
    account_id: str | None = None
    contact_id: str | None = None
    pipeline: str = "default"
    stage: DealStage = "new"
    amount: float = Field(default=0, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    probability_pct: int = Field(default=0, ge=0, le=100)
    expected_close_date: datetime | None = None
    owner_id: str | None = None
    lost_reason: str | None = None


class DealPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    account_id: str | None = None
    contact_id: str | None = None
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    probability_pct: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: datetime | None = None
    owner_id: str | None = None


class DealStageChange(BaseModel):
    """`lost` requires a reason (§2, acceptance #2)."""

    stage: DealStage
    lost_reason: str | None = None


# --- activities --------------------------------------------------------------

class EntityRef(BaseModel):
    type: EntityType
    id: str


class ActivityCreate(BaseModel):
    entity_ref: EntityRef
    type: ActivityType
    subject: str = Field(min_length=1)
    body: str | None = None
    due_at: datetime | None = None
    done: bool = False
    owner_id: str | None = None


class ActivityPatch(BaseModel):
    type: ActivityType | None = None
    subject: str | None = Field(default=None, min_length=1)
    body: str | None = None
    due_at: datetime | None = None
    done: bool | None = None
    owner_id: str | None = None
