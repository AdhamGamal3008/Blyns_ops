"""CRM's CSV column specs (docs/modules/CRM.md §7).

One `CsvEntity` per importable tab. Its `fields` list is the *only* place a
column is declared: the import template, the export column picker and the
import parser all read it, so a template can always be filled in and uploaded,
and any export round-trips back in as an upsert.

Relationship columns are deliberately human-writable — `account_name`,
`contact_email`, `owner_email` — because nobody can hand-type an ObjectId into
a spreadsheet. They are resolved by lookup at import time; an unknown value is
a row error rather than a silently created record (see csv_service.py).
"""

from __future__ import annotations

from app.modules.crm import repository as repo
from app.modules.crm.permissions import (
    ACCOUNT_STATUSES,
    LEAD_STATUSES,
    STAGES,
    TERMINAL_STAGES,
)
from app.shared.csv_io import CsvField
from app.shared.csv_spec import CsvEntity, CsvRef, RowRejected

USERS = "users"  # tenant employees, for `owner_email`


# --- row guards: what the API refuses, a spreadsheet must also refuse --------

def _guard_lead(doc: dict, existing: dict | None) -> None:
    if existing is not None and existing.get("status") == "converted":
        raise RowRejected(
            "This lead has already been converted and can no longer be edited."
        )


def _guard_deal(doc: dict, existing: dict | None) -> None:
    stage = doc.get("stage") or (existing or {}).get("stage") or "new"
    if existing is not None and existing.get("stage") in TERMINAL_STAGES:
        if stage != existing["stage"]:
            raise RowRejected(
                f"This deal is already {existing['stage']}; "
                "terminal stages cannot be reopened.",
                column="Stage",
            )
    reason = doc.get("lost_reason") or (existing or {}).get("lost_reason")
    if stage == "lost" and not (reason or "").strip():
        raise RowRejected(
            "A deal in the `lost` stage needs a lost reason.",
            column="Lost reason",
        )


# --- shared column shapes ----------------------------------------------------

OWNER_REF = CsvRef(
    key="owner_email", doc_key="owner_id", collection=USERS,
    match_field="email", label="Employee", store_str=True,
)
ACCOUNT_REF = CsvRef(
    key="account_name", doc_key="account_id", collection=repo.ACCOUNTS,
    match_field="name", label="Account",
)
CONTACT_REF = CsvRef(
    key="contact_email", doc_key="contact_id", collection=repo.CONTACTS,
    match_field="email", label="Contact", fold_case=False,
)


def _owner_field() -> CsvField:
    return CsvField(
        key="owner_email", header="Owner email", kind="email",
        # Deliberately blank in the sample row: no example address exists in
        # any real tenant, so a filled-in one would make the template you just
        # downloaded fail to upload. Blank is also the friendlier default.
        example="",
        hint="An employee of this company. Blank means you.",
    )


def _record_fields() -> tuple[CsvField, ...]:
    """Export-only provenance columns. Never importable — `id` and the
    timestamps are the database's to set, and letting a CSV name a record's id
    would let one tenant's file address another's row."""
    return (
        CsvField(key="id", header="Record ID", importable=False),
        CsvField(key="created_at", header="Created at", kind="datetime",
                 importable=False),
        CsvField(key="updated_at", header="Updated at", kind="datetime",
                 importable=False),
    )


# --- accounts ----------------------------------------------------------------

ACCOUNTS = CsvEntity(
    name="accounts",
    label="Accounts",
    collection=repo.ACCOUNTS,
    natural_key=("name",),
    status_field="status",
    status_choices=tuple(ACCOUNT_STATUSES),
    search_fields=("name",),
    create_defaults={"status": "prospect", "tags": []},
    refs=(OWNER_REF,),
    fields=(
        CsvField(key="name", header="Name", required=True, example="Globex Corp",
                 hint="Matched against existing accounts to update rather than duplicate."),
        CsvField(key="industry", header="Industry", example="Manufacturing"),
        CsvField(key="website", header="Website", example="https://globex.example"),
        CsvField(key="phone", header="Phone", example="+1 555 0100"),
        CsvField(key="status", header="Status", kind="enum",
                 choices=tuple(ACCOUNT_STATUSES), example="prospect"),
        CsvField(key="tags", header="Tags", kind="list", example="key-account; emea",
                 hint="Separate multiple tags with a semicolon."),
        CsvField(key="address.street", header="Address", example="1 Industrial Way"),
        CsvField(key="address.city", header="City", example="Springfield"),
        CsvField(key="address.state", header="State/Region", example="OR"),
        CsvField(key="address.postal_code", header="Postal code", example="97477"),
        CsvField(key="address.country", header="Country", example="USA"),
        _owner_field(),
        *_record_fields(),
    ),
)


# --- contacts ----------------------------------------------------------------

CONTACTS = CsvEntity(
    name="contacts",
    label="Contacts",
    collection=repo.CONTACTS,
    natural_key=("email",),
    search_fields=("first_name", "last_name", "email"),
    create_defaults={"tags": []},
    refs=(ACCOUNT_REF, OWNER_REF),
    fields=(
        CsvField(key="first_name", header="First name", required=True, example="Hank"),
        CsvField(key="last_name", header="Last name", required=True, example="Scorpio"),
        CsvField(key="email", header="Email", kind="email", example="hank@globex.example",
                 hint="Identifies the contact — a matching email updates that "
                      "contact instead of adding a second one."),
        CsvField(key="phone", header="Phone", example="+1 555 0111"),
        CsvField(key="title", header="Job title", example="VP Operations"),
        CsvField(key="account_name", header="Account", example="Globex Corp",
                 hint="Must already exist — import Accounts first."),
        CsvField(key="tags", header="Tags", kind="list", example="decision-maker"),
        _owner_field(),
        *_record_fields(),
    ),
)


# --- leads -------------------------------------------------------------------

LEADS = CsvEntity(
    name="leads",
    label="Leads",
    collection=repo.LEADS,
    natural_key=("email",),
    status_field="status",
    status_choices=tuple(LEAD_STATUSES),
    search_fields=("name",),
    row_guard=_guard_lead,
    create_defaults={
        "status": "new",
        "converted_to": {"account_id": None, "contact_id": None, "deal_id": None},
    },
    refs=(OWNER_REF,),
    fields=(
        CsvField(key="name", header="Name", required=True, example="Jane Prospect"),
        CsvField(key="email", header="Email", kind="email", example="jane@prospect.example",
                 hint="Identifies the lead on re-import."),
        CsvField(key="phone", header="Phone", example="+1 555 0122"),
        CsvField(key="source", header="Source", example="referral"),
        CsvField(
            key="status", header="Status", kind="enum",
            choices=tuple(LEAD_STATUSES),
            # `converted` is the outcome of POST /leads/{id}/convert, which
            # creates a linked account+contact+deal. Typing it into a
            # spreadsheet would mark a lead converted with nothing behind it.
            import_choices=tuple(s for s in LEAD_STATUSES if s != "converted"),
            example="new",
            hint="Convert leads from the Leads tab, not from a spreadsheet.",
        ),
        _owner_field(),
        *_record_fields(),
    ),
)


# --- deals -------------------------------------------------------------------

DEALS = CsvEntity(
    name="deals",
    label="Deals",
    collection=repo.DEALS,
    natural_key=("title", "account_name"),
    status_field="stage",
    status_choices=tuple(STAGES),
    date_fields=("created_at", "updated_at", "expected_close_date"),
    default_sort=("expected_close_date", 1),
    search_fields=("title",),
    row_guard=_guard_deal,
    create_defaults={
        "pipeline": "default", "stage": "new", "amount": 0.0,
        "currency": "USD", "probability_pct": 0, "lost_reason": None,
    },
    refs=(ACCOUNT_REF, CONTACT_REF, OWNER_REF),
    fields=(
        CsvField(key="title", header="Title", required=True, example="Globex rollout"),
        CsvField(key="account_name", header="Account", example="Globex Corp",
                 hint="Title + account identify the deal on re-import."),
        CsvField(key="contact_email", header="Contact email", kind="email",
                 example="hank@globex.example",
                 hint="Must already exist — import Contacts first."),
        CsvField(key="pipeline", header="Pipeline", example="default"),
        CsvField(key="stage", header="Stage", kind="enum", choices=tuple(STAGES),
                 example="new"),
        CsvField(key="amount", header="Amount", kind="float", example="25000"),
        CsvField(key="currency", header="Currency", example="USD"),
        CsvField(key="probability_pct", header="Probability %", kind="int",
                 example="40"),
        CsvField(key="expected_close_date", header="Expected close date", kind="date",
                 example="2026-09-30", hint="ISO format: YYYY-MM-DD."),
        CsvField(key="lost_reason", header="Lost reason", example="",
                 hint="Required when the stage is `lost`."),
        _owner_field(),
        CsvField(key="closed_at", header="Closed at", kind="datetime",
                 importable=False),
        *_record_fields(),
    ),
)


ENTITIES: dict[str, CsvEntity] = {
    e.name: e for e in (ACCOUNTS, CONTACTS, LEADS, DEALS)
}
