"""DBManager + audit/activity writers against a real (ephemeral) Mongo."""

from __future__ import annotations

from app.core.audit import write_activity, write_admin_audit
from app.core.db import close_db_manager, init_db_manager


async def test_ping_and_tenant_db_caching(db_manager):
    assert await db_manager.ping() is True
    a = db_manager.tenant("test_tenant_acme")
    b = db_manager.tenant("test_tenant_acme")
    assert a is b  # cached — one client, cheap db selection
    assert db_manager.tenant("test_tenant_other") is not a


async def test_admin_audit_writer(mongo_uri):
    manager = init_db_manager(mongo_uri)
    try:
        await write_admin_audit(
            actor_id="admin1",
            action="company.onboarded",
            target={"type": "company", "id": "c1"},
            details={"slug": "acme"},
        )
        doc = await manager.control.admin_audit_log.find_one({"actor_id": "admin1"})
        assert doc is not None
        assert doc["action"] == "company.onboarded"
        assert doc["target"] == {"type": "company", "id": "c1"}
        assert doc["occurred_at"] is not None
    finally:
        close_db_manager()


async def test_activity_writer_shape(db_manager):
    tenant_db = db_manager.tenant("test_tenant_acme")
    await write_activity(
        tenant_db,
        actor_id="user1",
        action="project.created",
        entity={"type": "project", "id": "p1", "label": "Website Revamp"},
        details={},
        actor_name="Jane Doe",
        module="projects",
    )
    doc = await tenant_db.activity_log.find_one({"actor_id": "user1"})
    assert doc is not None
    # exact activity document shape from docs/ARCHITECTURE.md §5
    assert doc["action"] == "project.created"
    assert doc["actor_name"] == "Jane Doe"
    assert doc["module"] == "projects"
    assert doc["entity"]["label"] == "Website Revamp"
    assert doc["occurred_at"] is not None
