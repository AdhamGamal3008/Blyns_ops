"""Self-hosted IP -> country resolution (docs/IP_ACCESS_CONTROL_PLAN.md P3):
reads a local .mmdb via an injected reader and FAILS OPEN (None) whenever the
dataset/library is absent or a lookup errors."""

from __future__ import annotations

from app.control_plane.ip_access.geoip import (
    GeoIpResolver,
    _country_from_record,
    build_geoip_resolver,
)
from app.control_plane.ip_access.matcher import compile_rules, decide


class _FakeReader:
    def __init__(self, table: dict[str, object]) -> None:
        self._table = table

    def get(self, ip: str) -> object:
        return self._table.get(ip)


def test_resolver_returns_upper_cased_iso_code():
    r = GeoIpResolver(_FakeReader({"1.2.3.4": {"country": {"iso_code": "kp"}}}))
    assert r.enabled is True
    assert r.country("1.2.3.4") == "KP"


def test_unknown_ip_returns_none():
    assert GeoIpResolver(_FakeReader({})).country("9.9.9.9") is None


def test_registered_country_is_the_fallback():
    r = GeoIpResolver(_FakeReader({"1.1.1.1": {"registered_country": {"iso_code": "US"}}}))
    assert r.country("1.1.1.1") == "US"


def test_country_preferred_over_registered_country():
    rec = {"country": {"iso_code": "DE"}, "registered_country": {"iso_code": "US"}}
    assert _country_from_record(rec) == "DE"


def test_malformed_records_return_none():
    assert _country_from_record("not-a-dict") is None
    assert _country_from_record({"country": {}}) is None
    assert _country_from_record({"country": {"iso_code": ""}}) is None


def test_null_resolver_returns_none():
    r = GeoIpResolver(None)
    assert r.enabled is False
    assert r.country("1.2.3.4") is None


def test_lookup_error_fails_open():
    class Boom:
        def get(self, ip: str) -> object:
            raise RuntimeError("corrupt database")

    assert GeoIpResolver(Boom()).country("1.2.3.4") is None


def test_none_or_empty_ip_is_none():
    r = GeoIpResolver(_FakeReader({"": {"country": {"iso_code": "XX"}}}))
    assert r.country(None) is None
    assert r.country("") is None


def test_build_resolver_without_path_is_noop():
    assert build_geoip_resolver(None).enabled is False


def test_build_resolver_missing_file_fails_open(tmp_path):
    r = build_geoip_resolver(str(tmp_path / "does-not-exist.mmdb"))
    assert r.enabled is False
    assert r.country("1.2.3.4") is None


def test_resolved_country_feeds_the_matcher():
    """The P4 call site: resolve the country, then hand it to `decide`."""
    resolver = GeoIpResolver(_FakeReader({"5.6.7.8": {"country": {"iso_code": "KP"}}}))
    ruleset = compile_rules([
        {"_id": "1", "kind": "deny", "match_type": "country", "value": "KP", "enabled": True},
    ])
    blocked = "5.6.7.8"
    assert decide(blocked, ruleset, country=resolver.country(blocked)).allowed is False
    # an IP the dataset doesn't know → no country → cannot be country-denied
    assert decide("9.9.9.9", ruleset, country=resolver.country("9.9.9.9")).allowed is True
