"""The shared CSV import & export engine (docs/modules/CRM.md §7,
docs/modules/INVENTORY.md §7).

Module-agnostic: it is driven entirely by a registry of `CsvEntity` (see
`shared/csv_spec.py`), so a module gets the whole surface — template, export,
two-phase import — by declaring its columns. CRM and Inventory both run this
code; there is deliberately no second copy.

It keeps to the rules each module's service enforces. Soft-deleted rows are
invisible, and per-entity `row_guard`s reject what the API would reject, so a
spreadsheet can never be used to get around a business rule. Where writing a
record does more than insert its document — Inventory's movements claim stock
and can be refused for insufficient stock — the entity supplies a `writer` and
the create goes through the module's own service.

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
   import of the same file updates the same records instead of doubling them —
   except for an `append_only` ledger, where a repeat genuinely means more
   entries and there is no key to match on.
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
from pymongo.errors import DuplicateKeyError

from app.core import storage
from app.core.audit import write_activity
from app.core.config import settings
from app.core.errors import TENANT_NOT_FOUND, VALIDATION_ERROR, DomainError
from app.shared import csv_io
from app.shared.csv_io import CsvField, CsvFormatError, RowIssue
from app.shared.csv_spec import CsvEntity, RowRejected
from app.shared.schemas import CsvExportQuery
from app.tenant.deps import ClientPrincipal

_LIVE = {"is_deleted": {"$ne": True}}
_EXPORT_BATCH = 500
_MAX_REPORTED_ERRORS = 500
_READ_CHUNK = 256 * 1024

# Projected alongside the natural key so a `row_guard` can inspect the record it
# is about to update. Cheap, and a superset is harmless — a guard reading a key
# that is not here simply sees None.
_GUARD_FIELDS = ("status", "stage", "is_active")


Registry = dict[str, CsvEntity]


def entity_for(registry: Registry, module: str, name: str) -> CsvEntity:
    entity = registry.get(name)
    if entity is None:
        raise DomainError(
            TENANT_NOT_FOUND,
            f"“{name}” is not a {module} data set. Choose one of: "
            + ", ".join(registry),
            http_status=404,
        )
    return entity


def entity_for_import(registry: Registry, module: str, name: str) -> CsvEntity:
    """Same, but refuses an export-only data set — one derived from another
    source of truth, which hand-written rows must not be able to overwrite."""
    entity = entity_for(registry, module, name)
    if not entity.can_import:
        raise DomainError(
            VALIDATION_ERROR,
            f"{entity.label} are derived and cannot be imported. "
            "Export them for reporting, and change the records they are "
            "computed from instead.",
            http_status=422,
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
        # The UI hides Import entirely for a derived data set, and tells an
        # append-only one that a repeat import adds rather than updates.
        "importable": entity.can_import,
        "append_only": entity.append_only,
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
    return csv_io.template_text(entity.importable_fields, sample=sample)


def filename_for(module: str, entity: CsvEntity, kind: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return f"{module}-{entity.name}-{kind}-{stamp}.csv"


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
        status_field = entity.field(entity.status_field)
        # A flag column ("Active": yes/no) is stored as a boolean, so the string
        # the picker sends would never match. Read it as its own declared kind.
        if status_field is not None and status_field.kind == "bool":
            query[entity.status_field] = csv_io.coerce(status_field, params.status)
        else:
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


def _key_part(entity: CsvEntity, value: Any) -> str:
    return _fold(value) if entity.key_fold else str(value)


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

    # An append-only ledger has nothing to match against: every row is a new
    # entry, so the index would be built and never read.
    if entity.append_only or not entity.natural_key:
        return index

    # Natural-key index for upsert, plus the fields the guards need.
    projection = dict.fromkeys(_GUARD_FIELDS, 1)
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
            parts.append(_key_part(entity, raw))
    return tuple(parts)


def _row_key(entity: CsvEntity, values: dict, resolved: dict) -> tuple | None:
    """The natural key of a row in the uploaded file, or None when there is
    nothing to match on.

    An append-only entity declares no natural key, and an empty tuple is NOT a
    usable one: every row would share it, so the second row of a ledger import
    would look like a repeat of the first and be counted as an update.
    """
    if entity.append_only or not entity.natural_key:
        return None
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
            parts.append(_key_part(entity, raw))
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
            raise RowRejected(
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
    *, module: str, filename: str, mode: Literal["validate", "commit"],
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
            if entity.row_guard is not None:
                entity.row_guard(fields, existing)
        except RowRejected as exc:
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
        created, updated, write_issues = await _apply(principal, entity, plan, actor)
        issues.extend(write_issues)

    # Audit is written by the caller (submit/approve/reject), not here, so the
    # feed can distinguish a direct commit from an approved one from a request.
    issues.sort(key=lambda i: i.row)
    return {
        "entity": entity.name,
        "label": entity.label,
        "mode": mode,
        "status": "committed" if mode == "commit" else "validated",
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


# --- import approval workflow (SETTINGS.md §1.3) ------------------------------
#
# A holder who may import but may not approve cannot commit directly: the file
# is staged in GridFS and a `csv_imports` request records the dry-run preview
# for an approver to act on. An approver's own import commits immediately.

_IMPORT_REQUESTS = "csv_imports"
_IMPORT_BUCKET = "import_files"


def _import_entity(action: str, module: str, entity: CsvEntity) -> dict:
    return {"type": f"{module}_import", "id": entity.name,
            "label": f"{entity.label} import"}


async def _log_import(
    principal: ClientPrincipal, module: str, action: str, entity: CsvEntity,
    details: dict,
) -> None:
    await write_activity(
        principal.tenant_db, actor_id=str(principal.user["_id"]),
        action=action, entity=_import_entity(action, module, entity),
        details=details, actor_name=principal.user["name"], module=module,
    )


def _counts(report: dict) -> dict:
    return {k: report[k] for k in ("rows", "created", "updated", "failed", "columns")}


async def submit_import(
    principal: ClientPrincipal, entity: CsvEntity, data: bytes,
    *, module: str, filename: str, can_approve: bool,
) -> dict[str, Any]:
    """The `mode=commit` path. An approver commits at once; anyone else has the
    file staged and a pending request opened for approval."""
    if can_approve:
        report = await import_csv(
            principal, entity, data, module=module, filename=filename, mode="commit",
        )
        await _log_import(principal, module, f"{module}.import.completed", entity, {
            "entity": entity.name, "file": filename, **_counts(report),
        })
        return report

    # stage: dry-run for the preview, then persist the file + a pending request
    preview = await import_csv(
        principal, entity, data, module=module, filename=filename, mode="validate",
    )
    db = principal.tenant_db
    stored = await storage.save_bytes(
        db, data, filename=filename, content_type="text/csv",
        uploaded_by=str(principal.user["_id"]), bucket_name=_IMPORT_BUCKET,
    )
    now = datetime.now(UTC)
    doc = {
        "module": module, "entity": entity.name, "status": "pending",
        "file_id": stored.file_id, "filename": filename,
        "requested_by": str(principal.user["_id"]),
        "requested_by_name": principal.user["name"],
        "requested_at": now,
        "preview": {
            **_counts(preview),
            "ignored_columns": preview["ignored_columns"],
            "errors": preview["errors"], "errors_truncated": preview["errors_truncated"],
        },
        "decided_by": None, "decided_by_name": None, "decided_at": None,
        "result": None, "reject_reason": None,
        "created_at": now, "updated_at": now, "is_deleted": False,
    }
    res = await db[_IMPORT_REQUESTS].insert_one(doc)
    await _log_import(principal, module, f"{module}.import.requested", entity, {
        "entity": entity.name, "file": filename, "request_id": str(res.inserted_id),
        **_counts(preview),
    })
    return {
        "status": "pending_approval",
        "request_id": str(res.inserted_id),
        "entity": entity.name, "label": entity.label, "file": filename,
        **{k: preview[k] for k in (
            "rows", "created", "updated", "failed", "columns",
            "ignored_columns", "errors", "errors_truncated",
        )},
    }


def _request_public(doc: dict) -> dict:
    """A request as the inbox/status views see it (no internal file id)."""
    return {
        "id": str(doc["_id"]),
        "module": doc["module"], "entity": doc["entity"], "status": doc["status"],
        "filename": doc.get("filename"),
        "requested_by": doc.get("requested_by"),
        "requested_by_name": doc.get("requested_by_name"),
        "requested_at": doc.get("requested_at"),
        "preview": doc.get("preview") or {},
        "decided_by_name": doc.get("decided_by_name"),
        "decided_at": doc.get("decided_at"),
        "reject_reason": doc.get("reject_reason"),
        "result": doc.get("result"),
    }


async def list_import_requests(
    principal: ClientPrincipal, module: str, *, mine: bool, status: str | None,
    approvable_entities: set[str],
) -> list[dict]:
    """Requests for a module. `mine` returns the caller's own (any status);
    otherwise the approver inbox: pending requests whose entity the caller can
    approve. `approvable_entities` is the set of entity names the caller may
    approve in this module (computed by the router from csv_access)."""
    db = principal.tenant_db
    query: dict[str, Any] = {"module": module, "is_deleted": {"$ne": True}}
    if mine:
        query["requested_by"] = str(principal.user["_id"])
        if status:
            query["status"] = status
    else:
        query["status"] = status or "pending"
        query["entity"] = {"$in": sorted(approvable_entities)}
    docs = await db[_IMPORT_REQUESTS].find(query).sort("requested_at", -1).to_list(500)
    return [_request_public(d) for d in docs]


async def load_request(
    principal: ClientPrincipal, module: str, request_id: str
) -> dict:
    doc = await principal.tenant_db[_IMPORT_REQUESTS].find_one({
        "_id": _oid(request_id, "import request"), "module": module,
        "is_deleted": {"$ne": True},
    })
    if doc is None:
        raise DomainError(TENANT_NOT_FOUND, "Import request not found.", 404)
    return doc


async def approve_import_request(
    principal: ClientPrincipal, entity: CsvEntity, module: str, request_id: str,
) -> dict[str, Any]:
    """Commit a pending request. The file is re-read and re-validated against
    *current* data (it may have moved since the request), so approval commits
    what is true now, not a stale snapshot."""
    doc = await load_request(principal, module, request_id)
    if doc["status"] != "pending":
        raise DomainError(
            VALIDATION_ERROR,
            f"This request was already {doc['status']}.", http_status=409,
        )
    db = principal.tenant_db
    grid_out, _, _ = await storage.open_download(
        db, doc["file_id"], bucket_name=_IMPORT_BUCKET
    )
    data = await grid_out.read()
    report = await import_csv(
        principal, entity, data, module=module,
        filename=doc["filename"], mode="commit",
    )
    now = datetime.now(UTC)
    await db[_IMPORT_REQUESTS].update_one({"_id": doc["_id"]}, {"$set": {
        "status": "approved", "decided_by": str(principal.user["_id"]),
        "decided_by_name": principal.user["name"], "decided_at": now,
        "result": _counts(report), "updated_at": now,
    }})
    await storage.delete_file(db, doc["file_id"], bucket_name=_IMPORT_BUCKET)
    await _log_import(principal, module, f"{module}.import.approved", entity, {
        "entity": entity.name, "file": doc["filename"], "request_id": request_id,
        "requested_by": doc.get("requested_by_name"), **_counts(report),
    })
    return {**report, "status": "approved", "request_id": request_id}


async def reject_import_request(
    principal: ClientPrincipal, entity: CsvEntity, module: str, request_id: str,
    reason: str,
) -> dict[str, Any]:
    doc = await load_request(principal, module, request_id)
    if doc["status"] != "pending":
        raise DomainError(
            VALIDATION_ERROR,
            f"This request was already {doc['status']}.", http_status=409,
        )
    db = principal.tenant_db
    now = datetime.now(UTC)
    await db[_IMPORT_REQUESTS].update_one({"_id": doc["_id"]}, {"$set": {
        "status": "rejected", "decided_by": str(principal.user["_id"]),
        "decided_by_name": principal.user["name"], "decided_at": now,
        "reject_reason": reason, "updated_at": now,
    }})
    await storage.delete_file(db, doc["file_id"], bucket_name=_IMPORT_BUCKET)
    await _log_import(principal, module, f"{module}.import.rejected", entity, {
        "entity": entity.name, "file": doc["filename"], "request_id": request_id,
        "requested_by": doc.get("requested_by_name"), "reason": reason,
    })
    return _request_public({**doc, "status": "rejected", "reject_reason": reason,
                            "decided_by_name": principal.user["name"],
                            "decided_at": now})


async def open_request_file(
    principal: ClientPrincipal, module: str, request_id: str
):
    """Stream the staged CSV so an approver can inspect the actual rows."""
    doc = await load_request(principal, module, request_id)
    grid_out, filename, content_type = await storage.open_download(
        principal.tenant_db, doc["file_id"], bucket_name=_IMPORT_BUCKET
    )
    return grid_out, filename, content_type


async def _apply(
    principal: ClientPrincipal, entity: CsvEntity, plan: list[_Planned], actor: str,
) -> tuple[int, int, list[RowIssue]]:
    """Write the planned rows.

    A row can still fail here, and not every failure is knowable earlier: an
    Inventory movement is refused for insufficient stock only at the moment it
    claims it. Such a row is reported like any other bad row and the rest of the
    file still lands — the same "import the good, report the bad" contract as
    the parse stage.
    """
    db = principal.tenant_db
    created = updated = 0
    fresh: dict[tuple, ObjectId] = {}
    issues: list[RowIssue] = []
    owned = any(ref.doc_key == "owner_id" for ref in entity.refs)

    for planned in plan:
        target = planned.existing_id or (
            fresh.get(planned.key) if planned.key is not None else None
        )
        try:
            if target is None:
                doc = dict(planned.fields)
                doc["created_by"] = actor
                # Only where the module actually models ownership — adding an
                # owner_id to a product would invent a field its API never sets.
                if owned:
                    doc.setdefault("owner_id", actor)
                if entity.writer is not None:
                    # The record has effects beyond its own document, so the
                    # module's service owns the write.
                    await entity.writer(principal, doc)
                else:
                    inserted = await _insert(db, entity.collection, doc)
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
            await _update(db, entity.collection, target, fields)
            updated += 1
        except DomainError as exc:
            issues.append(RowIssue(planned.row, None, "", exc.message))
        except DuplicateKeyError:
            # A unique index the natural key does not cover, or two rows racing
            # for the same one. Report it rather than 500 the whole import.
            issues.append(RowIssue(
                planned.row, None, "",
                "A record with this unique value already exists.",
            ))

    return created, updated, issues


# --- generic document writes -------------------------------------------------
#
# Deliberately not a module's repository: the engine serves several modules and
# must not import any one of them. The shape matches what every module's
# repository writes (BUILD.md §5 base fields), so a CSV-written document is
# indistinguishable from an API-written one.

async def _insert(db: AsyncIOMotorDatabase, coll: str, doc: dict) -> dict:
    now = datetime.now(UTC)
    doc.setdefault("created_at", now)
    doc.setdefault("updated_at", now)
    doc.setdefault("is_deleted", False)
    result = await db[coll].insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def _update(
    db: AsyncIOMotorDatabase, coll: str, oid: ObjectId, fields: dict
) -> None:
    fields["updated_at"] = datetime.now(UTC)
    await db[coll].update_one({"_id": oid}, {"$set": fields})
