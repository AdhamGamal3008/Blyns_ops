"""IP access matching engine (docs/IP_ACCESS_CONTROL_PLAN.md §2-B, §7.2 D2).

Pure and deterministic. Precedence (locked decision D2):

    1. an ALLOW rule matches      → allow   (allowlist always wins)
    2. a DENY ip/cidr rule matches → deny
    3. a DENY country rule matches → deny
    4. otherwise                   → allow   (default-allow posture, D1)

Geo resolution (IP → country) is NOT done here — the caller passes the already
resolved country (or None). That keeps this engine free of the geo-IP dataset
(which lands in P3) and trivially unit-testable. Rules are compiled once into an
in-memory `RuleSet`; `decide` never parses a network per request.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from dataclasses import dataclass, field

_Network = ipaddress.IPv4Network | ipaddress.IPv6Network
_Address = ipaddress.IPv4Address | ipaddress.IPv6Address


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str  # "allowlisted" | "denied" | "default_allow" | "unresolved"
    rule_id: str | None = None
    kind: str | None = None        # allow | deny
    match_type: str | None = None  # ip | cidr | country
    value: str | None = None


@dataclass(frozen=True)
class _CompiledRule:
    rule_id: str | None
    kind: str
    match_type: str
    value: str
    network: _Network | None  # set for ip/cidr, None for country

    def decision(self) -> Decision:
        return Decision(
            allowed=self.kind == "allow",
            reason="allowlisted" if self.kind == "allow" else "denied",
            rule_id=self.rule_id, kind=self.kind,
            match_type=self.match_type, value=self.value,
        )


@dataclass
class RuleSet:
    allow_networks: list[_CompiledRule] = field(default_factory=list)
    deny_networks: list[_CompiledRule] = field(default_factory=list)
    allow_countries: dict[str, _CompiledRule] = field(default_factory=dict)
    deny_countries: dict[str, _CompiledRule] = field(default_factory=dict)


def compile_rules(rules: Iterable[dict]) -> RuleSet:
    """Split enabled rules into fast-lookup buckets. Defensively skips
    deleted/disabled rows and any value that no longer parses, so a bad row can
    never break evaluation."""
    rs = RuleSet()
    for rule in rules:
        if rule.get("is_deleted") or rule.get("enabled") is False:
            continue
        kind = rule.get("kind")
        match_type = rule.get("match_type")
        value = rule.get("value")
        if kind not in ("allow", "deny") or not value:
            continue
        rule_id = str(rule["_id"]) if rule.get("_id") is not None else None

        if match_type in ("ip", "cidr"):
            try:
                network = ipaddress.ip_network(value, strict=False)
            except ValueError:
                continue
            compiled = _CompiledRule(rule_id, kind, match_type, value, network)
            (rs.allow_networks if kind == "allow" else rs.deny_networks).append(compiled)
        elif match_type == "country":
            compiled = _CompiledRule(rule_id, kind, match_type, value.upper(), None)
            bucket = rs.allow_countries if kind == "allow" else rs.deny_countries
            bucket[value.upper()] = compiled
    return rs


def _match_network(addr: _Address, rules: list[_CompiledRule]) -> _CompiledRule | None:
    for rule in rules:
        # `addr in network` is False (never raises) across IP families
        if rule.network is not None and addr in rule.network:
            return rule
    return None


def decide(ip: str | None, ruleset: RuleSet, country: str | None = None) -> Decision:
    """Evaluate one client IP (+ its resolved country, if any) against the rules."""
    addr: _Address | None = None
    if ip:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            addr = None

    code = country.upper() if country else None

    # 1. allowlist wins — ip/cidr, then country
    if addr is not None:
        hit = _match_network(addr, ruleset.allow_networks)
        if hit is not None:
            return hit.decision()
    if code and code in ruleset.allow_countries:
        return ruleset.allow_countries[code].decision()

    # 2/3. deny — ip/cidr, then country
    if addr is not None:
        hit = _match_network(addr, ruleset.deny_networks)
        if hit is not None:
            return hit.decision()
    if code and code in ruleset.deny_countries:
        return ruleset.deny_countries[code].decision()

    # 4. default allow (fail-open — an unparseable IP evaluates to allow too)
    reason = "unresolved" if ip and addr is None else "default_allow"
    return Decision(allowed=True, reason=reason)
