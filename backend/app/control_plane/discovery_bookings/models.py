"""Discovery-booking payloads + validation (docs/LANDING_PAGE.md §4).

Public lead capture from the marketing site. Everything is validated at the edge
so a malformed submission is a 422, never a bad row. Email is checked with a
pragmatic regex (no `email-validator` dependency). `website` is a honeypot — a
real user never sees or fills it; a non-empty value is dropped silently by the
router and never stored.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

INDUSTRIES: tuple[str, ...] = (
    "interior_fit_out", "flooring", "wall_cladding",
    "custom_furniture", "general_contractor", "other",
)
COMPANY_SIZES: tuple[str, ...] = ("1-10", "11-50", "51-200", "201-500", "500+")
STATUSES: tuple[str, ...] = ("new", "contacted", "scheduled", "closed")

Industry = Literal[
    "interior_fit_out", "flooring", "wall_cladding",
    "custom_furniture", "general_contractor", "other",
]
CompanySize = Literal["1-10", "11-50", "51-200", "201-500", "500+"]
BookingStatus = Literal["new", "contacted", "scheduled", "closed"]

# Pragmatic shape check — not full RFC 5322, just enough to reject typos and junk
# at the edge without pulling in a validator dependency.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class BookingCreate(BaseModel):
    """Public POST body. Required: name, work email, company, industry."""

    full_name: str = Field(min_length=1, max_length=120)
    work_email: str = Field(min_length=3, max_length=200)
    company: str = Field(min_length=1, max_length=160)
    industry: Industry
    phone: str | None = Field(default=None, max_length=40)
    company_size: CompanySize | None = None
    preferred_at: datetime | None = None
    message: str | None = Field(default=None, max_length=2000)
    # Honeypot — hidden in the UI; bots fill it. Accepted but never stored.
    website: str = Field(default="", max_length=200)

    @field_validator("full_name", "company", "phone", "message", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("work_email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        text = v.strip().lower()
        if not _EMAIL_RE.match(text):
            raise ValueError("work_email must be a valid email address")
        return text

    @property
    def is_honeypot(self) -> bool:
        return bool(self.website.strip())


class BookingUpdate(BaseModel):
    """Admin PATCH body — move the lead through its pipeline and/or append a note.
    At least one of `status` / `note` must be present."""

    status: BookingStatus | None = None
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("note", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _at_least_one(self) -> BookingUpdate:
        if self.status is None and not (self.note or "").strip():
            raise ValueError("provide a status and/or a note")
        return self
