"""Discovery-booking payload validation (docs/LANDING_PAGE.md §4).

Fast unit tests over the pydantic models — no database. Cover edge normalization,
the email shape check, the honeypot flag, and the PATCH "at least one field" rule.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.control_plane.discovery_bookings.models import BookingCreate, BookingUpdate


def _valid(**over: object) -> dict:
    base: dict = {
        "full_name": "Dana Cole",
        "work_email": "Dana@Acme.com",
        "company": "Acme Interiors",
        "industry": "interior_fit_out",
    }
    base.update(over)
    return base


def test_valid_booking_normalizes() -> None:
    b = BookingCreate(**_valid(full_name="  Dana Cole  ", phone="  123  "))
    assert b.full_name == "Dana Cole"          # stripped
    assert b.work_email == "dana@acme.com"     # stripped + lowercased
    assert b.phone == "123"
    assert b.is_honeypot is False


@pytest.mark.parametrize("email", ["not-an-email", "a@b", "@x.com", "a b@x.com", "x@y."])
def test_bad_email_rejected(email: str) -> None:
    with pytest.raises(ValidationError):
        BookingCreate(**_valid(work_email=email))


def test_missing_required_field_rejected() -> None:
    with pytest.raises(ValidationError):
        BookingCreate(full_name="X", work_email="x@y.com", company="C")  # no industry


def test_blank_name_rejected() -> None:
    with pytest.raises(ValidationError):
        BookingCreate(**_valid(full_name="   "))


@pytest.mark.parametrize(
    ("field", "value"),
    [("industry", "aerospace"), ("company_size", "enormous")],
)
def test_bad_enum_rejected(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        BookingCreate(**_valid(**{field: value}))


def test_honeypot_flag() -> None:
    assert BookingCreate(**_valid()).is_honeypot is False
    assert BookingCreate(**_valid(website="http://spam.example")).is_honeypot is True


def test_update_requires_status_or_note() -> None:
    with pytest.raises(ValidationError):
        BookingUpdate()
    with pytest.raises(ValidationError):
        BookingUpdate(note="   ")
    assert BookingUpdate(status="contacted").status == "contacted"
    assert BookingUpdate(note="Called them").note == "Called them"


@pytest.mark.parametrize("status", ["nope", "open", "done"])
def test_update_bad_status_rejected(status: str) -> None:
    with pytest.raises(ValidationError):
        BookingUpdate(status=status)
