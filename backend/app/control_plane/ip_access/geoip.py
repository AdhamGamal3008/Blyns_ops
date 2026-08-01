"""Self-hosted IP -> country resolution (docs/IP_ACCESS_CONTROL_PLAN.md P3).

Country geo-blocking needs to map an IP to an ISO country code. Per the project
non-negotiables this must be **fully self-hosted** — no external API call, ever.
We read a local MaxMind-format database (`.mmdb`; GeoLite2 Country or DB-IP Lite)
with the open-source `maxminddb` reader, loaded into memory once.

Everything here **fails open**: if the reader library is not installed, the
`.mmdb` path is unset/missing, or a lookup errors, the resolver returns `None`.
`None` means "country unknown", so the matcher can never *deny* on country — the
safe default. Country blocking activates only once ops provisions the dataset and
sets `ERP_IP_GEOIP_DB_PATH`.

Refresh: geo-IP data goes stale, so the `.mmdb` should be refreshed on a schedule
(monthly is typical). The operational flow is: replace the file, then `reload()`
(or restart the process). The dataset's license/attribution is an ops concern
recorded alongside the file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class Reader(Protocol):
    """The slice of `maxminddb.Reader` we use — `.get(ip)` returns the record
    dict (or None). Declared as a Protocol so tests can inject a fake."""

    def get(self, ip: str) -> object: ...


def _country_from_record(record: object) -> str | None:
    """Pull the ISO-3166 alpha-2 code out of a GeoLite2/DB-IP country record,
    falling back to `registered_country` when `country` is absent."""
    if not isinstance(record, dict):
        return None
    for key in ("country", "registered_country"):
        section = record.get(key)
        if isinstance(section, dict):
            code = section.get("iso_code")
            if isinstance(code, str) and code:
                return code.upper()
    return None


class GeoIpResolver:
    """Resolves IP -> country via an injected `.mmdb` reader. A resolver with no
    reader (the default when geo-IP is not configured) always returns None."""

    def __init__(self, reader: Reader | None = None) -> None:
        self._reader = reader

    @property
    def enabled(self) -> bool:
        return self._reader is not None

    def country(self, ip: str | None) -> str | None:
        if self._reader is None or not ip:
            return None
        try:
            return _country_from_record(self._reader.get(ip))
        except Exception:  # a bad lookup must never break a request
            return None


def open_mmdb_reader(path: str) -> Reader | None:
    """Open a `.mmdb` file with the `maxminddb` reader. Returns None (logged) if
    the library is missing or the file cannot be opened — the caller then runs
    with country rules inert."""
    if not path or not Path(path).is_file():
        logger.warning("geoip: database path %r missing; country rules inert.", path)
        return None
    try:
        import maxminddb  # optional dependency (pyproject extra: geoip)
    except ImportError:
        logger.warning("geoip: `maxminddb` not installed; country rules inert.")
        return None
    try:
        return maxminddb.open_database(path)
    except Exception as exc:  # corrupt/incompatible file, permissions, …
        logger.warning("geoip: could not open %r (%s); country rules inert.", path, exc)
        return None


def build_geoip_resolver(db_path: str | None) -> GeoIpResolver:
    """Factory: a working resolver when the dataset is present, else a no-op
    (fail-open) resolver. Safe to call at startup regardless of configuration."""
    if not db_path:
        return GeoIpResolver(None)
    return GeoIpResolver(open_mmdb_reader(db_path))
