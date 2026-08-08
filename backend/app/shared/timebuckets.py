"""Month bucketing shared by the per-module analytics surfaces
(docs/PROJECT_ANALYTICS_PLAN.md). Pure, read-only helpers — no I/O."""

from __future__ import annotations

from datetime import UTC, datetime


def month_buckets(now: datetime, count: int) -> list[str]:
    """The last `count` months as 'YYYY-MM', oldest first, incl. the current."""
    year, month, out = now.year, now.month, []
    for _ in range(count):
        out.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(out))


def window_start(now: datetime, count: int) -> datetime:
    """UTC midnight on day 1 of the oldest month in a `count`-month window — the
    lower bound whose `>=` covers the current month plus the prior count-1."""
    index = (now.year * 12 + now.month - 1) - (count - 1)
    year, month0 = divmod(index, 12)
    return datetime(year, month0 + 1, 1, tzinfo=UTC)
