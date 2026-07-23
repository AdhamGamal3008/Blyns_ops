"""Mongo-backed rate-limit store (docs/ARCHITECTURE.md §6, ENVIRONMENTS.md §4):
the production limiter must hold ONE limit across many workers, so the counter
lives in Mongo, not in per-process memory."""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.rate_limit import (
    InMemoryFixedWindowStore,
    MongoFixedWindowStore,
    ensure_bucket_indexes,
    ensure_enforcement_indexes,
)


async def test_mongo_store_shares_the_count_across_instances(db_manager):
    """Two store instances = two workers pointed at the same control DB. Their
    increments accumulate into one window count, so the limit can't be evaded
    by spreading requests across workers."""
    control = db_manager.control
    await ensure_enforcement_indexes(control)
    await control.rate_limit_windows.delete_many({})

    worker_a = MongoFixedWindowStore(control)
    worker_b = MongoFixedWindowStore(control)

    # alternate workers hitting the same (ip, window)
    assert await worker_a.incr("1.2.3.4", 100) == 1
    assert await worker_b.incr("1.2.3.4", 100) == 2
    assert await worker_a.incr("1.2.3.4", 100) == 3
    assert await worker_b.incr("1.2.3.4", 100) == 4

    # a different window is an independent counter
    assert await worker_a.incr("1.2.3.4", 101) == 1
    # a different key too
    assert await worker_b.incr("9.9.9.9", 100) == 1


async def test_mongo_store_persists_one_doc_per_key_window(db_manager):
    control = db_manager.control
    await ensure_enforcement_indexes(control)
    await control.rate_limit_windows.delete_many({})

    store = MongoFixedWindowStore(control)
    for _ in range(5):
        await store.incr("5.5.5.5", 200)

    doc = await control.rate_limit_windows.find_one({"key": "5.5.5.5", "window": 200})
    assert doc["count"] == 5
    assert "created_at" in doc  # TTL field so old windows self-expire
    assert await control.rate_limit_windows.count_documents({"key": "5.5.5.5"}) == 1


async def test_in_memory_store_counts_within_a_window():
    store = InMemoryFixedWindowStore()
    assert await store.incr("ip", 1) == 1
    assert await store.incr("ip", 1) == 2
    assert await store.incr("ip", 2) == 1  # new window resets


async def test_ensure_bucket_indexes_heals_pre_index_duplicates(db_manager):
    """Regression: a collection poisoned by pre-index upsert races (duplicate
    {scope,key,minute} rows) must still get its unique index. ensure_bucket_indexes
    merges each duplicate group into one doc — summing the counters so no request
    accounting is lost — then builds the index. Without the self-heal the build
    fails with E11000 forever and the guarantee is silently absent."""
    buckets = db_manager.control.rate_limit_buckets
    await buckets.drop()  # start with no index, no docs

    minute = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)

    def bucket(requests: int, rate_limited: int) -> dict:
        return {"scope": "platform", "key": "platform", "minute": minute,
                "requests": requests, "rate_limited": rate_limited}

    # three racing inserts for the same key tuple, as pre-index upserts would
    await buckets.insert_many([bucket(5, 1), bucket(3, 0), bucket(2, 2)])

    await ensure_bucket_indexes(db_manager.control)

    # collapsed to one doc, counters summed (nothing lost)
    docs = await buckets.find(
        {"scope": "platform", "key": "platform", "minute": minute}
    ).to_list(length=None)
    assert len(docs) == 1
    assert docs[0]["requests"] == 10
    assert docs[0]["rate_limited"] == 3

    # the unique index now exists and rejects a further duplicate
    info = await buckets.index_information()
    assert info["scope_1_key_1_minute_1"]["unique"] is True

    # idempotent: a second run is a clean no-op
    await ensure_bucket_indexes(db_manager.control)
    assert await buckets.count_documents(
        {"scope": "platform", "key": "platform", "minute": minute}
    ) == 1
