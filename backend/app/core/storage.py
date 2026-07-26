"""Self-hosted file storage for project documents (docs/modules/
PROJECT_MANAGEMENT.md §3.7).

Files live in GridFS inside the **tenant's own database** — the same
per-tenant isolation every other collection gets — so nothing leaves the box
and no managed object store is involved (BUILD.md non-negotiable #1). The size
cap is enforced while reading so a large upload can't exhaust memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorGridFSBucket

from app.core.errors import TENANT_NOT_FOUND, VALIDATION_ERROR, DomainError

_BUCKET = "deliverable_files"
_READ_CHUNK = 256 * 1024


class _Upload(Protocol):
    """The bits of Starlette's UploadFile that storage needs."""

    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...


@dataclass
class StoredFile:
    file_id: str
    filename: str
    content_type: str
    size: int


def bucket(
    db: AsyncIOMotorDatabase, bucket_name: str = _BUCKET
) -> AsyncIOMotorGridFSBucket:
    return AsyncIOMotorGridFSBucket(db, bucket_name=bucket_name)


async def save_bytes(
    db: AsyncIOMotorDatabase, data: bytes, *, filename: str, content_type: str,
    uploaded_by: str, bucket_name: str = _BUCKET,
) -> StoredFile:
    """Store already-buffered bytes in a named GridFS bucket. Used where the
    caller already holds the content (a validated CSV import staged for
    approval) rather than an incoming UploadFile stream."""
    file_id = await bucket(db, bucket_name).upload_from_stream(
        filename, data,
        metadata={"content_type": content_type, "uploaded_by": uploaded_by},
    )
    return StoredFile(str(file_id), filename, content_type, len(data))


async def delete_file(
    db: AsyncIOMotorDatabase, file_id: str, bucket_name: str = _BUCKET
) -> None:
    """Best-effort removal of a stored file (a rejected/consumed import)."""
    try:
        oid = ObjectId(file_id)
    except (InvalidId, TypeError):
        return
    try:
        await bucket(db, bucket_name).delete(oid)
    except Exception:
        pass  # already gone — nothing to unwind


async def save_upload(
    db: AsyncIOMotorDatabase, upload: _Upload, *, uploaded_by: str, max_bytes: int
) -> StoredFile:
    """Buffer an upload up to `max_bytes`, then store it in the tenant GridFS.

    Buffering (rather than streaming straight in) keeps GridFS clean of aborted
    half-writes and lets us reject an oversize file before persisting anything.
    """
    data = bytearray()
    while True:
        chunk = await upload.read(_READ_CHUNK)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_bytes:
            raise DomainError(
                VALIDATION_ERROR,
                f"File exceeds the {max_bytes // (1024 * 1024)} MB upload limit.",
                http_status=413,
            )
    if not data:
        raise DomainError(VALIDATION_ERROR, "The uploaded file is empty.", http_status=422)

    filename = (upload.filename or "upload").strip() or "upload"
    content_type = upload.content_type or "application/octet-stream"
    file_id = await bucket(db).upload_from_stream(
        filename, bytes(data),
        metadata={"content_type": content_type, "uploaded_by": uploaded_by},
    )
    return StoredFile(str(file_id), filename, content_type, len(data))


async def file_metadata(db: AsyncIOMotorDatabase, file_id: str) -> StoredFile | None:
    """Stored handle for a GridFS file id (filename/type/size), or None if the
    id is malformed or unknown. Used to denormalize file info onto a document."""
    try:
        oid = ObjectId(file_id)
    except (InvalidId, TypeError):
        return None
    f = await db[f"{_BUCKET}.files"].find_one({"_id": oid})
    if f is None:
        return None
    meta = f.get("metadata") or {}
    return StoredFile(
        str(oid), f.get("filename") or "upload",
        meta.get("content_type", "application/octet-stream"),
        int(f.get("length") or 0),
    )


async def open_download(
    db: AsyncIOMotorDatabase, file_id: str, bucket_name: str = _BUCKET
):
    """Open a GridFS download stream; raises 404 if the file id is unknown.

    Returns `(grid_out, filename, content_type)`. Read `grid_out` in chunks via
    `await grid_out.read(n)` for a streaming response.
    """
    try:
        oid = ObjectId(file_id)
    except (InvalidId, TypeError):
        raise DomainError(VALIDATION_ERROR, "Malformed file id.", http_status=422) from None
    try:
        grid_out = await bucket(db, bucket_name).open_download_stream(oid)
    except Exception:
        raise DomainError(TENANT_NOT_FOUND, "File not found.", http_status=404) from None
    meta = grid_out.metadata or {}
    return grid_out, grid_out.filename or "download", meta.get(
        "content_type", "application/octet-stream"
    )


async def read_chunks(grid_out):
    """Async generator over a GridFS download stream, for StreamingResponse."""
    while True:
        chunk = await grid_out.read(_READ_CHUNK)
        if not chunk:
            break
        yield chunk
