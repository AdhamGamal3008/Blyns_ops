"""Project Documents (docs/modules/PROJECT_MANAGEMENT.md §3.7): the deliverables
section as a team document store — GridFS file uploads and URL references, each
carrying uploader/source/stage/timestamp, with optional referencing from a
stage's file-submission gate."""

from __future__ import annotations

from app.modules.projects import service

BASE = "/api/v1/projects"


async def _project(client_client, name="Docs Project") -> str:
    res = await client_client.post(BASE, json={"name": name, "planned_budget": 1000})
    assert res.status_code == 201, res.text
    return res.json()["data"]["id"]


async def _upload(client_client, pid, data=b"PDF-BYTES-\x00\x01", filename="spec.pdf",
                  ct="application/pdf") -> dict:
    res = await client_client.post(
        f"{BASE}/{pid}/deliverables/files", files={"file": (filename, data, ct)}
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def test_upload_create_and_download_roundtrip(client_client):
    pid = await _project(client_client)
    payload = b"binary-drawing-\x00\xff" * 50
    handle = await _upload(client_client, pid, data=payload, filename="drawing.dwg",
                           ct="application/acad")
    assert handle["size"] == len(payload)
    assert handle["filename"] == "drawing.dwg"

    res = await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "shop_drawing", "title": "Lobby drawing",
        "source_type": "upload", "file_id": handle["file_id"],
    })
    assert res.status_code == 201, res.text
    doc = res.json()["data"]
    ver = doc["versions"][0]
    assert ver["source_type"] == "upload"
    assert ver["file_id"] == handle["file_id"]
    assert ver["content_type"] == "application/acad"
    assert ver["size"] == len(payload)
    assert doc["uploaded_by"]  # resolved to a real user name

    dl = await client_client.get(f"{BASE}/{pid}/deliverables/{doc['id']}/download")
    assert dl.status_code == 200, dl.text
    assert dl.content == payload  # bytes survive the round-trip
    assert "attachment" in dl.headers["content-disposition"]
    assert "drawing.dwg" in dl.headers["content-disposition"]


async def test_url_document_records_source_and_uploader(client_client):
    pid = await _project(client_client)
    res = await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "report", "title": "Design brief",
        "source_type": "url", "file_ref": "https://drive.example.com/brief.pdf",
    })
    assert res.status_code == 201, res.text
    doc = res.json()["data"]
    assert doc["source_type"] == "url"
    assert doc["versions"][0]["file_ref"] == "https://drive.example.com/brief.pdf"
    assert doc["uploaded_by"]
    assert doc["uploaded_at"]


async def test_missing_source_is_rejected(client_client):
    pid = await _project(client_client)
    # url source without a file_ref
    r1 = await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "report", "title": "No ref", "source_type": "url"})
    assert r1.status_code == 422, r1.text
    # upload source without a file_id
    r2 = await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "report", "title": "No file", "source_type": "upload"})
    assert r2.status_code == 422, r2.text


async def test_general_vs_stage_scoped_document(client_client):
    pid = await _project(client_client)
    # general project doc: no stage
    general = await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "report", "title": "General note",
        "source_type": "url", "file_ref": "vault://note"})
    assert general.status_code == 201
    assert general.json()["data"]["stage_key"] is None
    # stage-scoped doc
    scoped = await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "report", "title": "Stage note", "stage_key": "site_survey",
        "source_type": "url", "file_ref": "vault://note2"})
    assert scoped.status_code == 201
    assert scoped.json()["data"]["stage_key"] == "site_survey"
    # a bogus stage is rejected
    bad = await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "report", "title": "Bad", "stage_key": "not_a_stage",
        "source_type": "url", "file_ref": "vault://x"})
    assert bad.status_code == 422


async def test_supply_document_records_reference(client_client):
    pid = await _project(client_client)
    doc = (await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "shop_drawing", "title": "Contract PDF",
        "source_type": "url", "file_ref": "vault://contract"})).json()["data"]

    # satisfy a Stage-1 document gate, referencing that document as evidence
    res = await client_client.post(
        f"{BASE}/{pid}/stages/1/documents/contract_signed",
        json={"deliverable_id": doc["id"]},
    )
    assert res.status_code == 200, res.text

    stage = (await client_client.get(f"{BASE}/{pid}/stages/1")).json()["data"]
    refs = stage["instance"].get("document_refs") or []
    match = [r for r in refs if r["gate_key"] == "contract_signed"]
    assert len(match) == 1
    assert match[0]["deliverable_id"] == doc["id"]
    assert match[0]["title"] == "Contract PDF"
    assert match[0]["by"]  # who attached it
    assert match[0]["at"]  # when
    # the gate is still satisfied
    assert "contract_signed" in stage["instance"]["documents_supplied"]


async def test_supply_without_reference_still_works(client_client):
    pid = await _project(client_client)
    res = await client_client.post(
        f"{BASE}/{pid}/stages/1/documents/contract_signed", json={})
    assert res.status_code == 200, res.text
    stage = (await client_client.get(f"{BASE}/{pid}/stages/1")).json()["data"]
    assert "contract_signed" in stage["instance"]["documents_supplied"]
    assert not (stage["instance"].get("document_refs") or [])


async def test_download_url_version_is_rejected(client_client):
    pid = await _project(client_client)
    doc = (await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "report", "title": "Link only",
        "source_type": "url", "file_ref": "https://x/y.pdf"})).json()["data"]
    dl = await client_client.get(f"{BASE}/{pid}/deliverables/{doc['id']}/download")
    assert dl.status_code == 422  # a URL reference has no file to stream


async def test_upload_size_limit_enforced(client_client, monkeypatch):
    pid = await _project(client_client)
    monkeypatch.setattr(service.settings, "max_upload_mb", 0)  # any non-empty file over cap
    res = await client_client.post(
        f"{BASE}/{pid}/deliverables/files",
        files={"file": ("big.bin", b"x" * 2048, "application/octet-stream")},
    )
    assert res.status_code == 413, res.text


async def test_uploaded_revision_appends_new_file(client_client):
    pid = await _project(client_client)
    h1 = await _upload(client_client, pid, data=b"v1-bytes", filename="a.pdf")
    doc = (await client_client.post(f"{BASE}/{pid}/deliverables", json={
        "kind": "shop_drawing", "title": "Rev doc",
        "source_type": "upload", "file_id": h1["file_id"]})).json()["data"]

    h2 = await _upload(client_client, pid, data=b"v2-different-bytes", filename="b.pdf")
    rev = await client_client.post(
        f"{BASE}/{pid}/deliverables/{doc['id']}/revisions",
        json={"source_type": "upload", "file_id": h2["file_id"], "note": "clash fix"},
    )
    assert rev.status_code == 201, rev.text
    updated = rev.json()["data"]
    assert updated["current_version"] == 2
    assert len(updated["versions"]) == 2
    # each version keeps its own file; downloading v1 and v2 differ
    d1 = await client_client.get(f"{BASE}/{pid}/deliverables/{doc['id']}/download?version=1")
    d2 = await client_client.get(f"{BASE}/{pid}/deliverables/{doc['id']}/download?version=2")
    assert d1.content == b"v1-bytes"
    assert d2.content == b"v2-different-bytes"
