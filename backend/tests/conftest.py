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

import httpx  # noqa: E402
import pytest  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.db import DBManager  # noqa: E402
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
