"""What a module declares so the shared CSV engine can serve it.

`csv_io.py` knows how to read and write a CSV; this file describes *what* a
module's rows mean — which collection they live in, which columns stand in for
stored ids, what identifies an existing record. A module supplies a registry of
`CsvEntity` (see `modules/crm/csv_schema.py`, `modules/inventory/csv_schema.py`)
and `csv_service.py` does the rest.

Not every data set behaves like a plain document. Three flags cover the cases
the CRM's own entities never raised:

* `importable=False` — a derived view that must never be written by hand
  (Inventory's `stock_levels` is computed from the movement ledger).
* `append_only=True` — an immutable ledger, where a repeated import means more
  entries, not an update to old ones.
* `writer=…` — the record has side effects beyond its own document, so creating
  it has to go through the module's service rather than a raw insert.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any, Protocol

from app.shared.csv_io import CsvField


class RowRejected(Exception):
    """A row broke a business rule. Reported against that row; the rest of the
    file still imports."""

    def __init__(self, message: str, column: str | None = None, value: str = ""):
        super().__init__(message)
        self.column = column
        self.value = value


class _Principal(Protocol):
    """The bit of ClientPrincipal a writer needs, without importing the tenant
    layer into the shared package."""

    user: dict


RowGuard = Callable[[dict, dict | None], None]
"""(doc fields, existing doc or None) → raise RowRejected to refuse the row."""

RowWriter = Callable[[Any, dict], Awaitable[Any]]
"""(principal, doc fields) → create the record through the module's service."""


@dataclass(frozen=True)
class CsvRef:
    """A human-readable column standing in for a stored id."""

    key: str
    """CSV field key, e.g. `account_name`."""

    doc_key: str
    """Document field it resolves to, e.g. `account_id`."""

    collection: str
    match_field: str
    label: str

    fold_case: bool = True
    """Match ignoring case/outer whitespace (names). Codes and emails are
    exact — a SKU that differs only in case is a different SKU."""

    store_str: bool = False
    """`owner_id` is stored as a string everywhere in CRM; account and contact
    references are stored as ObjectIds. Keep both shapes identical to what the
    module's service writes, or the two write paths diverge."""


@dataclass(frozen=True)
class CsvEntity:
    name: str
    label: str
    collection: str
    fields: tuple[CsvField, ...]
    refs: tuple[CsvRef, ...] = ()

    natural_key: tuple[str, ...] = ()
    """Field keys that identify an existing record for upsert. A row whose key
    columns are blank can never match, so it is always created. Empty for an
    append-only ledger."""

    key_fold: bool = True
    """Match the natural key ignoring case. True for names a person types
    ("globex corp"); False for exact identifiers backed by a unique index — a
    folded match on `products.sku` would let a re-import silently rename it."""

    importable: bool = True
    """False makes this export-only: no template, and the import route refuses
    it. For views derived from another source of truth."""

    append_only: bool = False
    """Every row creates. For an immutable ledger, where a correction is a new
    entry rather than an edit of an old one."""

    writer: RowWriter | None = None
    """Route creates through the module's service. Required whenever writing the
    record does more than insert its document — claiming stock, posting a
    balancing entry — because a raw insert would skip those effects and leave
    the module's own invariants broken."""

    row_guard: RowGuard | None = None
    """Business rules the module's API enforces, applied to a spreadsheet row so
    a CSV cannot do what the API refuses."""

    status_field: str | None = None
    status_choices: tuple[str, ...] = ()
    date_fields: tuple[str, ...] = ("created_at", "updated_at")
    default_sort: tuple[str, int] = ("created_at", -1)

    search_fields: tuple[str, ...] = ()
    """Document fields the export's `q` filter scans — the same ones the
    module's list endpoints search, so the two never disagree."""

    create_defaults: dict[str, Any] = dc_field(default_factory=dict)
    """Applied to rows the import creates, for columns the file left out. These
    mirror the Pydantic defaults in the module's models.py; a document written
    by CSV must be shaped exactly like one written by POST."""

    @property
    def can_import(self) -> bool:
        return self.importable

    @property
    def importable_fields(self) -> tuple[CsvField, ...]:
        return tuple(f for f in self.fields if f.importable)

    @property
    def exportable(self) -> tuple[CsvField, ...]:
        return tuple(f for f in self.fields if f.exportable)

    def field(self, key: str) -> CsvField | None:
        return next((f for f in self.fields if f.key == key), None)

    def ref(self, key: str) -> CsvRef | None:
        return next((r for r in self.refs if r.key == key), None)
