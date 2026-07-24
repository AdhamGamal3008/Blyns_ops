"""CRM CSV import & export (docs/modules/CRM.md §7).

Split out of service.py because it is a second write path into the same
collections and deserves to be read as one piece. It keeps to the rules
service.py enforces — soft-deleted rows are invisible, a converted lead is
frozen, a terminal deal cannot be reopened — so a spreadsheet can never be used
to get around a business rule the API refuses.

Import is two-phase. `mode=validate` reads and reports without writing;
`mode=commit` performs the same read and then applies it. The client keeps the
file and posts it twice, which keeps the server free of half-finished import
state.

Three behaviors worth stating plainly, because they are what make a round trip
(export → edit in Excel → re-import) safe:

1. **A column absent from the file is never touched.** Export three columns,
   edit them, re-import: the other fields keep their stored values.
2. **A blank cell means "nothing supplied", not "erase this".** On create it
   falls back to the field's default; on update the stored value stands.
   Clearing a field is done in the UI, where it is unambiguous.
3. **Matching is on a natural key, never on a row's position or id.** A second
   import of the same file updates the same records instead of doubling them.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime, time, timedelta
from typing import Any, Literal

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.audit import write_activity
from app.core.config import settings
from app.core.errors import TENANT_NOT_FOUND, VALIDATION_ERROR, DomainError
from app.modules.crm import repository as repo
from app.modules.crm.csv_schema import ENTITIES, CsvEntity
from app.modules.crm.models import CsvExportQuery
from app.modules.crm.permissions import TERMINAL_STAGES
from app.shared import csv_io
from app.shared.csv_io import CsvField, CsvFormatError, RowIssue
from app.tenant.deps import ClientPrincipal

_LIVE = {"is_deleted": {"$ne": True}}
_EXPORT_BATCH = 500
_MAX_REPORTED_ERRORS = 500
_READ_CHUNK = 256 * 1024


def entity_for(name: str) -> CsvEntity:
    entity = ENTITIES.get(name)
    if entity is None:
        raise DomainError(
            TENANT_NOT_FOUND,
            f"“{name}” is not a CRM data set. Choose one of: "
            + ", ".join(ENTITIES),
            http_status=404,
        )
    return entity


def _oid(value: Any, what: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise DomainError(VALIDATION_ERROR, f"Malformed {what} id.", 422) from None


# --- metadata (drives the export column picker and the import dialog) --------

def describe(entity: CsvEntity) -> dict[str, Any]:
    def field_json(f: CsvField) -> dict[str, Any]:
        return {
            "key": f.key, "header": f.header, "kind": f.kind,
            "required": f.required, "choices": list(f.choices),
            "importable": f.importable, "exportable": f.exportable,
            "example": f.example, "hint": f.hint,
        }

    status_field = entity.field(entity.status_field or "")
    return {
        "entity": entity.name,
        "label": entity.label,
        "fields": [field_json(f) for f in entity.fields],
        "filters": {
            "status": None if status_field is None else {
                "label": status_field.header,
                "choices": list(entity.status_choices),
            },
            "date_fields": [
                {"key": key, "label": (entity.field(key) or _fallback(key)).header}
                for key in entity.date_fields
            ],
            "supports_search": bool(entity.search_fields),
            "supports_owner": True,
        },
    }


def _fallback(key: str) -> CsvField:
    return CsvField(key=key, header=key.replace("_", " ").capitalize())


def template(entity: CsvEntity, *, sample: bool) -> str:
    return csv_io.template_text(entity.importable, sample=sample)


def filename_for(entity: CsvEntity, kind: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return f"crm-{entity.name}-{kind}-{stamp}.csv"


# --- export ------------------------------------------------------------------

def select_fields(entity: CsvEntity, requested: str | None) -> list[CsvField]:
    """Resolve `?fields=name,status` against the spec, keeping spec order so
    two exports of the same selection are always column-identical."""
    if not requested or not requested.strip():
        return list(entity.exportable)
    wanted = {part.strip() for part in requested.split(",") if part.strip()}
    known = {f.key for f in entity.exportable}
    unknown = sorted(wanted - known)
    if unknown:
        raise DomainError(
            VALIDATION_ERROR,
            f"Unknown column(s) for {entity.label}: {', '.join(unknown)}.",
            http_status=422,
        )
    selected = [f for f in entity.exportable if f.key in wanted]
    if not selected:
        raise DomainError(VALIDATION_ERROR, "Select at least one column.", 422)
    return selected


def export_query(
    principal: ClientPrincipal, entity: CsvEntity, params: CsvExportQuery
) -> dict[str, Any]:
    """Build the Mongo filter. Validated here, before the streaming response
    starts — once bytes are on the wire an error can no longer be reported."""
    query: dict[str, Any] = dict(_LIVE)

    if params.owner == "mine":
        query["owner_id"] = str(principal.user["_id"])

    if params.status:
        if entity.status_field is None:
            raise DomainError(
                VALIDATION_ERROR, f"{entity.label} have no status to filter on.", 422
            )
        if params.status not in entity.status_choices:
            raise DomainError(
                VALIDATION_ERROR,
                f"“{params.status}” is not one of: "
                + ", ".join(entity.status_choices),
                http_status=422,
            )
        query[entity.status_field] = params.status

    if params.q and entity.search_fields:
        query["$or"] = [
            {f: {"$regex": params.q, "$options": "i"}} for f in entity.search_fields
        ]

    if params.account_id:
        if entity.ref("account_name") is None:
            raise DomainError(
                VALIDATION_ERROR, f"{entity.label} are not linked to an account.", 422
            )
        query["account_id"] = _oid(params.account_id, "account")

    date_field = params.date_field or entity.date_fields[0]
    if date_field not in entity.date_fields:
        raise DomainError(
            VALIDATION_ERROR,
            f"“{date_field}” is not a date column on {entity.label}. Choose one of: "
            + ", ".join(entity.date_fields),
            http_status=422,
        )
    window: dict[str, datetime] = {}
    if params.date_from:
        window["$gte"] = datetime.combine(params.date_from, time.min, tzinfo=UTC)
    if params.date_to:
        # `to` is the last day the user wants included, so run to its end.
        window["$lt"] = datetime.combine(
            params.date_to + timedelta(days=1), time.min, tzinfo=UTC
        )
    if window:
        if params.date_from and params.date_to and params.date_to < params.date_from:
            raise DomainError(
                VALIDATION_ERROR, "The date range ends before it starts.", 422
            )
        query[date_field] = window

    return query


async def _resolve_refs(
    db: AsyncIOMotorDatabase, entity: CsvEntity, selected: list[CsvField],
    docs: list[dict],
) -> dict[str, dict[str, Any]]:
    """id → human value, one `$in` per reference column per batch."""
    keys = {f.key for f in selected}
    maps: dict[str, dict[str, Any]] = {}
    for ref in entity.refs:
        if ref.key not in keys:
            continue
        ids: set[ObjectId] = set()
        for doc in docs:
            raw = doc.get(ref.doc_key)
            if not raw:
                continue
            try:
                ids.add(ObjectId(raw))
            except (InvalidId, TypeError):
                continue
        found: dict[str, Any] = {}
        if ids:
            cursor = db[ref.collection].find(
                {"_id": {"$in": list(ids)}}, {ref.match_field: 1}
            )
            async for referenced in cursor:
                found[str(referenced["_id"])] = referenced.get(ref.match_field)
        maps[ref.key] = found
    return maps


def _export_row(
    entity: CsvEntity, doc: dict, selected: list[CsvField],
    ref_maps: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for f in selected:
        if f.key == "id":
            row["id"] = str(doc.get("_id", ""))
            continue
        ref = entity.ref(f.key)
        if ref is not None:
            row[f.key] = ref_maps.get(f.key, {}).get(str(doc.get(ref.doc_key) or ""))
            continue
        if "." in f.key:
            parent, child = f.key.split(".", 1)
            nested = doc.get(parent)
            row[f.key] = nested.get(child) if isinstance(nested, dict) else None
            continue
        row[f.key] = doc.get(f.key)
    return row


async def export_stream(
    principal: ClientPrincipal, entity: CsvEntity, selected: list[CsvField],
    query: dict[str, Any],
) -> AsyncIterator[str]:
    """Stream the export in batches so a large tenant never lands in memory."""
    db = principal.tenant_db
    yield csv_io.header_line(selected)

    cursor = db[entity.collection].find(query).sort([entity.default_sort])
    batch: list[dict] = []
    async for doc in cursor:
        batch.append(doc)
        if len(batch) >= _EXPORT_BATCH:
            ref_maps = await _resolve_refs(db, entity, selected, batch)
            yield "".join(
                csv_io.data_line(selected, _export_row(entity, d, selected, ref_maps))
                for d in batch
            )
            batch = []
    if batch:
        ref_maps = await _resolve_refs(db, entity, selected, batch)
        yield "".join(
            csv_io.data_line(selected, _export_row(entity, d, selected, ref_maps))
            for d in batch
        )


# --- import ------------------------------------------------------------------

class _RowError(Exception):
    def __init__(self, message: str, column: str | None = None, value: str = ""):
        super().__init__(message)
        self.column = column
        self.value = value


@dataclass
class _Index:
    """Everything an import needs to look up, loaded once instead of per row.

    Each map is keyed by a folded string, so `globex corp` finds `Globex Corp`.
    Loading the whole (projected) collection trades memory for one query per
    reference instead of one per row — with the row cap at
    `settings.max_import_rows` that is the cheaper side of the trade.
    """

    refs: dict[str, dict[str, Any]] = dataclass_field(default_factory=dict)
    existing: dict[tuple, dict] = dataclass_field(default_factory=dict)


def _fold(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


async def _build_index(
    db: AsyncIOMotorDatabase, entity: CsvEntity, present: list[str]
) -> _Index:
    index = _Index()

    for ref in entity.refs:
        if ref.key not in present:
            continue
        lookup: dict[str, Any] = {}
        cursor = db[ref.collection].find(
            {"is_deleted": {"$ne": True}}, {ref.match_field: 1}
        )
        async for doc in cursor:
            raw = doc.get(ref.match_field)
            if raw in (None, ""):
                continue
            key = _fold(raw) if ref.fold_case else str(raw)
            # First writer wins, so a duplicate name resolves to the oldest
            # record rather than flip-flopping between imports.
            lookup.setdefault(key, str(doc["_id"]) if ref.store_str else doc["_id"])
        index.refs[ref.key] = lookup

    # Natural-key index for upsert, plus the fields the guards need.
    projection = {"status": 1, "stage": 1}
    for key_field in entity.natural_key:
        key_ref = entity.ref(key_field)
        projection[key_ref.doc_key if key_ref else key_field] = 1
    cursor = db[entity.collection].find({"is_deleted": {"$ne": True}}, projection)
    async for doc in cursor:
        stored = _stored_key(entity, doc)
        if stored is not None:
            index.existing.setdefault(stored, doc)
    return index


def _stored_key(entity: CsvEntity, doc: dict) -> tuple | None:
    """The natural key of a record already in the database."""
    parts: list[Any] = []
    for key in entity.natural_key:
        ref = entity.ref(key)
        if ref is not None:
            raw = doc.get(ref.doc_key)
            parts.append(str(raw) if raw else None)
        else:
            raw = doc.get(key)
            if raw in (None, ""):
                return None  # nothing to match on — always a new record
            parts.append(_fold(raw))
    return tuple(parts)


def _row_key(entity: CsvEntity, values: dict, resolved: dict) -> tuple | None:
    """The natural key of a row in the uploaded file."""
    parts: list[Any] = []
    for key in entity.natural_key:
        ref = entity.ref(key)
        if ref is not None:
            raw = resolved.get(ref.doc_key)
            parts.append(str(raw) if raw else None)
        else:
            raw = values.get(key)
            if raw in (None, ""):
                return None
            parts.append(_fold(raw))
    return tuple(parts)


def _resolve_row_refs(entity: CsvEntity, values: dict, index: _Index) -> dict:
    """Turn `account_name` / `contact_email` / `owner_email` into stored ids.

    An unknown value is a row error, never a quietly created record — a typo in
    a spreadsheet should not spawn a phantom account.
    """
    resolved: dict[str, Any] = {}
    for ref in entity.refs:
        if ref.key not in values:
            continue
        raw = values[ref.key]
        if raw in (None, ""):
            continue
        key = _fold(raw) if ref.fold_case else str(raw)
        found = index.refs.get(ref.key, {}).get(key)
        if found is None:
            f = entity.field(ref.key)
            raise _RowError(
                f"No {ref.label.lower()} matches “{raw}”. "
                f"Create it first, or correct the spelling.",
                column=f.header if f else ref.key,
                value=str(raw),
            )
        resolved[ref.doc_key] = found
    return resolved


def _doc_fields(
    entity: CsvEntity, values: dict, resolved: dict, *, creating: bool
) -> dict[str, Any]:
    """Map coerced cells onto document fields.

    Only keys the file actually carried a value for appear — see this module's
    docstring on absent columns and blank cells.
    """
    doc: dict[str, Any] = dict(entity.create_defaults) if creating else {}
    nested: dict[str, dict[str, Any]] = {}

    for key, value in values.items():
        if value is None or entity.ref(key) is not None:
            continue
        f = entity.field(key)
        if f is None or not f.importable:
            continue
        if "." in key:
            parent, child = key.split(".", 1)
            nested.setdefault(parent, {})[child] = value
        else:
            doc[key] = value

    doc.update(resolved)
    for parent, children in nested.items():
        doc[parent] = children
    return doc


def _validate_row(entity: CsvEntity, doc: dict, existing: dict | None) -> None:
    """The business rules service.py enforces, applied to a spreadsheet row."""
    if entity.name == "leads" and existing is not None:
        if existing.get("status") == "converted":
            raise _RowError(
                "This lead has already been converted and can no longer be edited."
            )

    if entity.name == "deals":
        stage = doc.get("stage") or (existing or {}).get("stage") or "new"
        if existing is not None and existing.get("stage") in TERMINAL_STAGES:
            if stage != existing["stage"]:
                raise _RowError(
                    f"This deal is already {existing['stage']}; "
                    "terminal stages cannot be reopened.",
                    column="Stage",
                )
        reason = doc.get("lost_reason") or (existing or {}).get("lost_reason")
        if stage == "lost" and not (reason or "").strip():
            raise _RowError(
                "A deal in the `lost` stage needs a lost reason.",
                column="Lost reason",
            )


@dataclass
class _Planned:
    row: int
    key: tuple | None
    existing_id: ObjectId | None
    fields: dict[str, Any]
    nested_parents: tuple[str, ...]


async def read_upload(upload: Any, *, max_bytes: int) -> bytes:
    """Buffer an uploaded CSV, refusing an oversize file before parsing it."""
    data = bytearray()
    while True:
        chunk = await upload.read(_READ_CHUNK)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_bytes:
            raise DomainError(
                VALIDATION_ERROR,
                f"The file is larger than the {max_bytes // (1024 * 1024)} MB "
                "import limit.",
                http_status=413,
            )
    if not data:
        raise DomainError(VALIDATION_ERROR, "The uploaded file is empty.", 422)
    return bytes(data)


async def import_csv(
    principal: ClientPrincipal, entity: CsvEntity, data: bytes,
    *, filename: str, mode: Literal["validate", "commit"],
) -> dict[str, Any]:
    db = principal.tenant_db
    actor = str(principal.user["_id"])

    try:
        parsed = csv_io.parse(
            data, entity.fields, max_rows=settings.max_import_rows
        )
    except CsvFormatError as exc:
        raise DomainError(VALIDATION_ERROR, str(exc), 422) from exc

    index = await _build_index(db, entity, parsed.present)
    issues: list[RowIssue] = list(parsed.issues)
    plan: list[_Planned] = []
    planned_keys: set[tuple] = set()
    created = updated = 0

    for prow in parsed.rows:
        try:
            resolved = _resolve_row_refs(entity, prow.values, index)
            key = _row_key(entity, prow.values, resolved)
            existing = index.existing.get(key) if key is not None else None
            # A key first seen earlier in this same file updates the record
            # that row created, rather than inserting a near-duplicate.
            repeat = existing is None and key is not None and key in planned_keys
            creating = existing is None and not repeat

            fields = _doc_fields(entity, prow.values, resolved, creating=creating)
            _validate_row(entity, fields, existing)
        except _RowError as exc:
            issues.append(RowIssue(prow.row, exc.column, exc.value, str(exc)))
            continue

        if creating:
            created += 1
            if key is not None:
                planned_keys.add(key)
        else:
            updated += 1
        plan.append(_Planned(
            row=prow.row,
            key=key,
            existing_id=existing["_id"] if existing else None,
            fields=fields,
            nested_parents=tuple(
                {k.split(".", 1)[0] for k in prow.values if "." in k} & fields.keys()
            ),
        ))

    if mode == "commit" and plan:
        created, updated = await _apply(db, entity, plan, actor)
        await write_activity(
            db, actor_id=actor, action="crm.import.completed",
            entity={"type": "crm_import", "id": entity.name,
                    "label": f"{entity.label} import"},
            details={
                "entity": entity.name, "file": filename,
                "created": created, "updated": updated,
                "failed": len(issues), "rows": parsed.seen_rows,
                "columns": parsed.present,
            },
            actor_name=principal.user["name"], module="crm",
        )

    return {
        "entity": entity.name,
        "label": entity.label,
        "mode": mode,
        "file": filename,
        "rows": parsed.seen_rows,
        "created": created,
        "updated": updated,
        "failed": len({issue.row for issue in issues}),
        "columns": parsed.present,
        "ignored_columns": parsed.unknown_headers,
        "errors": [
            {"row": i.row, "column": i.column, "value": i.value, "message": i.message}
            for i in issues[:_MAX_REPORTED_ERRORS]
        ],
        "errors_truncated": len(issues) > _MAX_REPORTED_ERRORS,
    }


async def _apply(
    db: AsyncIOMotorDatabase, entity: CsvEntity, plan: list[_Planned], actor: str,
) -> tuple[int, int]:
    created = updated = 0
    fresh: dict[tuple, ObjectId] = {}

    for planned in plan:
        target = planned.existing_id or (
            fresh.get(planned.key) if planned.key is not None else None
        )
        if target is None:
            doc = dict(planned.fields)
            doc["created_by"] = actor
            doc.setdefault("owner_id", actor)
            inserted = await repo.insert(db, entity.collection, doc)
            if planned.key is not None:
                fresh[planned.key] = inserted["_id"]
            created += 1
            continue

        fields = dict(planned.fields)
        # A nested column ($set "address.city") cannot create a path under a
        # stored null, so merge the sub-document rather than dotting into it.
        for parent in planned.nested_parents:
            stored = await db[entity.collection].find_one(
                {"_id": target}, {parent: 1}
            )
            current = (stored or {}).get(parent)
            fields[parent] = {
                **(current if isinstance(current, dict) else {}),
                **fields[parent],
            }
        fields["updated_by"] = actor
        await repo.update(db, entity.collection, target, fields)
        updated += 1

    return created, updated
