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


# Stage 1 · Project Initiation — the three required entry documents (v2.0).
STAGE1_DOCS = ("loi_or_po", "scope_boq_approved", "site_access_confirmed")


async def _clear_stage(client_client, pid, order, docs=()):
    """Attach evidence to a stage's document gates, submit, and approve it. An
    approver-less auto-advance stage (v2.0 Stage 2 · Site Survey) advances on
    submit alone, with no documents to attach and no approval step."""
    for key in docs:
        r = await client_client.post(
            f"{BASE}/{pid}/stages/{order}/documents/{key}/attach",
            json={"source_type": "url",
                  "file_ref": f"https://docs.example.com/{key}.pdf"},
        )
        assert r.status_code == 201, r.text
    submit = await client_client.post(f"{BASE}/{pid}/stages/{order}/submit", json={})
    assert submit.status_code == 200, submit.text
    if submit.json()["data"].get("auto_advanced"):
        return
    r = await client_client.post(f"{BASE}/{pid}/stages/{order}/approve", json={})
    assert r.status_code == 200, r.text


async def _reach_stage3(client_client, pid):
    """Walk the project to Stage 3 · Design Package, whose only entry gate is a
    dependency (survey_complete) — no document to attach."""
    await _clear_stage(client_client, pid, 1, STAGE1_DOCS)
    await _clear_stage(client_client, pid, 2)  # Site Survey auto-advances


async def _employee(client, client_client, slug: str, role_name: str, tag: str):
    """Create an employee holding `role_name` and return an auth header."""
    roles = (await client_client.get("/api/v1/settings/roles")).json()["data"]
    role_id = next(r["id"] for r in roles if r["name"] == role_name)
    email = f"{tag}@{slug}.com"
    res = await client_client.post("/api/v1/settings/employees", json={
        "name": f"{role_name} {tag}", "email": email, "role_id": role_id,
    })
    assert res.status_code == 201, res.text
    temp_pw = res.json()["data"]["temp_password"]
    res = await client.post("/api/v1/auth/login", json={
        "company": slug, "email": email, "password": temp_pw,
    })
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['data']['access_token']}"}


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
        f"{BASE}/{pid}/stages/1/documents/loi_or_po",
        json={"deliverable_id": doc["id"]},
    )
    assert res.status_code == 200, res.text

    stage = (await client_client.get(f"{BASE}/{pid}/stages/1")).json()["data"]
    refs = stage["instance"].get("document_refs") or []
    match = [r for r in refs if r["gate_key"] == "loi_or_po"]
    assert len(match) == 1
    assert match[0]["deliverable_id"] == doc["id"]
    assert match[0]["title"] == "Contract PDF"
    assert match[0]["by"]  # who attached it
    assert match[0]["at"]  # when
    # the gate is still satisfied
    assert "loi_or_po" in stage["instance"]["documents_supplied"]


async def test_document_gate_cannot_be_supplied_without_evidence(client_client):
    """A document gate is only satisfied by an attached file or URL — it can
    never be ticked off empty."""
    pid = await _project(client_client)
    res = await client_client.post(
        f"{BASE}/{pid}/stages/1/documents/loi_or_po", json={})
    assert res.status_code == 422, res.text
    assert "requires a document" in res.json()["error"]["message"]

    stage = (await client_client.get(f"{BASE}/{pid}/stages/1")).json()["data"]
    assert "loi_or_po" not in (stage["instance"]["documents_supplied"] or [])


async def test_non_document_gate_is_still_marked_without_a_file(client_client):
    """The evidence rule is scoped to document gates. A dependency gate — Stage
    3's survey_complete — has no file to attach, so it stays directly markable
    and must not 422."""
    pid = await _project(client_client)
    await _reach_stage3(client_client, pid)
    res = await client_client.post(
        f"{BASE}/{pid}/stages/3/documents/survey_complete", json={})
    assert res.status_code == 200, res.text


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


async def test_attach_uploaded_file_at_a_gate_satisfies_it(client_client):
    """The gate IS the document's identity: attaching asks for no kind and no
    stage — both are derived — and satisfies the gate in one step."""
    pid = await _project(client_client)
    payload = b"signed-contract-bytes"
    handle = await _upload(client_client, pid, data=payload, filename="contract.pdf")

    res = await client_client.post(
        f"{BASE}/{pid}/stages/1/documents/loi_or_po/attach",
        json={"source_type": "upload", "file_id": handle["file_id"]},
    )
    assert res.status_code == 201, res.text
    doc = res.json()["data"]["document"]
    # kind + stage derived from the gate, never asked for
    assert doc["kind"] == "certificate"
    assert doc["stage_key"] == "project_initiation"
    assert doc["gate_key"] == "loi_or_po"
    assert doc["title"] == "Loi or po"

    stage = (await client_client.get(f"{BASE}/{pid}/stages/1")).json()["data"]
    assert "loi_or_po" in stage["instance"]["documents_supplied"]
    ref = next(r for r in stage["instance"]["document_refs"]
               if r["gate_key"] == "loi_or_po")
    # the reference carries what an approver needs to open it
    assert ref["source_type"] == "upload"
    assert ref["deliverable_id"] == doc["id"]

    dl = await client_client.get(f"{BASE}/{pid}/deliverables/{doc['id']}/download")
    assert dl.status_code == 200
    assert dl.content == payload


async def test_attach_url_at_a_gate(client_client):
    pid = await _project(client_client)
    res = await client_client.post(
        f"{BASE}/{pid}/stages/1/documents/scope_boq_approved/attach",
        json={"source_type": "url", "file_ref": "https://drive.example.com/quote.pdf"},
    )
    assert res.status_code == 201, res.text
    stage = (await client_client.get(f"{BASE}/{pid}/stages/1")).json()["data"]
    ref = next(r for r in stage["instance"]["document_refs"]
               if r["gate_key"] == "scope_boq_approved")
    assert ref["source_type"] == "url"
    assert ref["file_ref"] == "https://drive.example.com/quote.pdf"


async def test_attach_rejects_unknown_and_non_document_gates(client_client):
    pid = await _project(client_client)
    # unknown gate
    bad = await client_client.post(
        f"{BASE}/{pid}/stages/1/documents/not_a_gate/attach",
        json={"source_type": "url", "file_ref": "https://x/y"})
    assert bad.status_code == 422

    # walk to Stage 3, whose entry gate is a dependency, not a document
    await _reach_stage3(client_client, pid)
    res = await client_client.post(
        f"{BASE}/{pid}/stages/3/documents/survey_complete/attach",
        json={"source_type": "url", "file_ref": "https://x/y"})
    assert res.status_code == 422
    assert "does not take a document" in res.json()["error"]["message"]


def test_bom_gate_maps_to_the_bom_kind():
    """Stage 5 (Material Procurement) finds the BOM by kind to reserve stock —
    the gate mapping must keep bom_present storing as `bom`."""
    from app.modules.projects.permissions import GATE_DOCUMENT_KINDS
    assert GATE_DOCUMENT_KINDS["bom_present"] == "bom"


async def test_read_user_can_open_gate_evidence(client, client_client, onboarded_company):
    """Downloading a document's file requires `projects` READ — a reviewer with
    read access can open the evidence attached to a stage."""
    slug = onboarded_company["slug"]
    pid = await _project(client_client)
    payload = b"contract-for-approver"
    handle = await _upload(client_client, pid, data=payload, filename="c.pdf")
    res = await client_client.post(
        f"{BASE}/{pid}/stages/1/documents/loi_or_po/attach",
        json={"source_type": "upload", "file_id": handle["file_id"]})
    did = res.json()["data"]["document"]["id"]

    role = await client_client.post("/api/v1/settings/roles", json={
        "name": "Reviewer", "permissions": {"dashboard": 2, "projects": 2},  # READ
    })
    assert role.status_code == 201, role.text
    reviewer = await _employee(client, client_client, slug, "Reviewer", "reviewer")
    dl = await client.get(f"{BASE}/{pid}/deliverables/{did}/download", headers=reviewer)
    assert dl.status_code == 200, dl.text
    assert dl.content == payload


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
