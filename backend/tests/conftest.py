"""Test fixtures (docs/TESTING.md §2).

Boots a throwaway `mongod` on a random port so tests NEVER touch a shared/dev
database. Test env vars are set here, before any app module is imported, so
`app.core.config.settings` is built with test values.
"""

from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import time

# --- test environment (must precede any `app.*` import) --------------------
os.environ.setdefault("ERP_ENV", "test")
os.environ.setdefault("ERP_JWT_SECRET", secrets.token_hex(32))  # random per run
os.environ.setdefault("ERP_CONTROL_DB_NAME", "erp_control_test")
os.environ.setdefault("ERP_TENANT_DB_PREFIX", "test_tenant_")
os.environ.setdefault("ERP_ACCESS_TOKEN_TTL_MIN", "5")
os.environ.setdefault("ERP_RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("ERP_IP_FILTER_ENABLED", "false")  # tests opt in per-case
os.environ.setdefault("ERP_DEFAULT_FAILED_LOGIN_THRESHOLD", "3")  # fast lockout tests
os.environ.setdefault("ERP_METRICS_INTERVAL_SEC", "0")  # no background collector loop

import uuid  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.db import DBManager, get_db_manager  # noqa: E402
from app.main import create_app  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"ephemeral mongod did not come up on port {port}")


@pytest.fixture(scope="session")
def mongo_uri(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Ephemeral mongod on a random port; killed (and data discarded) at session end."""
    mongod = shutil.which("mongod")
    if mongod is None:
        pytest.skip("mongod binary not found — install MongoDB to run integration tests")

    port = _free_port()
    dbpath = tmp_path_factory.mktemp("mongo-data")
    proc = subprocess.Popen(
        [mongod, "--dbpath", str(dbpath), "--port", str(port),
         "--bind_ip", "127.0.0.1", "--quiet"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(port)
        yield f"mongodb://127.0.0.1:{port}"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


@pytest.fixture
def test_settings(mongo_uri: str) -> Settings:
    # Reads the ERP_* test vars above; only the mongo URI is per-session dynamic.
    return Settings(mongo_uri=mongo_uri)


@pytest.fixture
async def db_manager(mongo_uri: str):
    manager = DBManager(mongo_uri)
    yield manager
    manager.close()


@pytest.fixture
async def app(test_settings: Settings):
    application = create_app(test_settings)
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- realm fixtures (docs/TESTING.md §2) -----------------------------------

ADMIN_EMAIL = "root@test.local"
ADMIN_PASSWORD = "RootPass123!"


@pytest.fixture
async def control_seeded(app):
    """Seeds admin roles + a Super Admin into the (ephemeral) control DB."""
    from app.control_plane.admin_users.repository import (
        create_admin_user,
        ensure_admin_indexes,
        seed_admin_roles,
    )
    from app.core.security import hash_password

    control = get_db_manager().control
    await ensure_admin_indexes(control)
    role_ids = await seed_admin_roles(control)
    await create_admin_user(
        control, ADMIN_EMAIL, "Root", hash_password(ADMIN_PASSWORD),
        role_ids["Super Admin"],
    )
    # The control DB persists across tests in the session mongod — reset any
    # state a previous test mutated (deactivation, lockout) so tests stay
    # order-independent.
    await control.admin_users.update_one(
        {"email": ADMIN_EMAIL},
        {"$set": {"is_active": True, "failed_attempts": 0, "locked_until": None}},
    )
    return {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "role_ids": role_ids}


@pytest.fixture
async def admin_client(app, client, control_seeded):
    """httpx client with a Super Admin bearer token."""
    res = await client.post("/api/v1/admin/auth/login", json={
        "email": control_seeded["email"], "password": control_seeded["password"],
    })
    assert res.status_code == 200, res.text
    token = res.json()["data"]["access_token"]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as c:
        yield c


@pytest.fixture
async def onboarded_company(app):
    """Onboards a uniquely-slugged company through the real provisioning
    engine; returns ids + the owner's temp password."""
    from app.control_plane.companies.models import (
        OnboardCompanyPayload,
        OwnerPayload,
        SecurityPolicy,
    )
    from app.control_plane.provisioning.engine import onboard_company

    slug = f"acme-{uuid.uuid4().hex[:6]}"
    result = await onboard_company(OnboardCompanyPayload(
        name="Acme Corp", slug=slug, seat_limit=10,
        enabled_modules=["dashboard", "settings", "projects", "crm", "inventory", "finance"],
        owner=OwnerPayload(name="Jane Doe", email=f"jane@{slug}.com"),
        security=SecurityPolicy(failed_login_threshold=3, lockout_minutes=15),
    ), actor_id="test-fixture")
    return {
        "company": result.company,
        "slug": slug,
        "owner_email": f"jane@{slug}.com",
        "temp_password": result.owner_temp_password,
    }


OWNER_PASSWORD = "OwnerPass123!"


@pytest.fixture
async def client_client(app, client, onboarded_company):
    """httpx client authenticated as the company Owner (forced reset done)."""
    login = {"company": onboarded_company["slug"],
             "email": onboarded_company["owner_email"]}
    res = await client.post("/api/v1/auth/login", json={
        **login, "password": onboarded_company["temp_password"],
    })
    assert res.status_code == 200, res.text
    first = res.json()["data"]
    assert first["password_reset_required"] is True
    res = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": onboarded_company["temp_password"],
              "new_password": OWNER_PASSWORD},
        headers={"Authorization": f"Bearer {first['access_token']}"},
    )
    assert res.status_code == 200, res.text
    res = await client.post("/api/v1/auth/login",
                            json={**login, "password": OWNER_PASSWORD})
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    ) as c:
        c.tokens = data  # type: ignore[attr-defined]
        yield c
