"""Database connection manager (docs/ARCHITECTURE.md §2).

The heart of multitenancy: ONE Motor client (one connection pool), many logical
databases. Never open a client per tenant — selecting a database is cheap.
A tenant's `db_name` is never guessed; it always comes from the company
registry via the tenant-resolution layer.
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings


class DBManager:
    def __init__(self, uri: str):
        # tz_aware: BSON dates come back as aware-UTC datetimes, so they can be
        # compared against datetime.now(UTC) (lockout windows, expiries).
        self._client: AsyncIOMotorClient = AsyncIOMotorClient(
            uri, uuidRepresentation="standard", tz_aware=True
        )
        self._tenant_cache: dict[str, AsyncIOMotorDatabase] = {}

    @property
    def control(self) -> AsyncIOMotorDatabase:
        return self._client[settings.control_db_name]

    def tenant(self, db_name: str) -> AsyncIOMotorDatabase:
        # db_name comes from the company registry, already prefixed
        if db_name not in self._tenant_cache:
            self._tenant_cache[db_name] = self._client[db_name]
        return self._tenant_cache[db_name]

    async def ping(self) -> bool:
        await self._client.admin.command("ping")
        return True

    def raw_client(self) -> AsyncIOMotorClient:
        return self._client  # used by metrics for serverStatus/dbStats

    def close(self) -> None:
        self._client.close()


# Process-wide singleton, initialized by the app lifespan (or by tests with an
# ephemeral URI). Modules that need a DB handle outside request scope (e.g. the
# audit writers) use get_db_manager().
_manager: DBManager | None = None


def init_db_manager(uri: str) -> DBManager:
    global _manager
    _manager = DBManager(uri)
    return _manager


def get_db_manager() -> DBManager:
    if _manager is None:
        raise RuntimeError("DBManager not initialized — call init_db_manager() first")
    return _manager


def close_db_manager() -> None:
    global _manager
    if _manager is not None:
        _manager.close()
        _manager = None
