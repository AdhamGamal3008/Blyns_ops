"""IP access rule payloads + value validation (docs/IP_ACCESS_CONTROL_PLAN.md §2-A).

A rule is an allow/deny that matches a single IP, a CIDR range, or a country code.
Values are validated and canonicalized here so a malformed IP/CIDR/country is a 422
at the edge, never a bad row in the store.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

IpRuleKind = Literal["allow", "deny"]
IpMatchType = Literal["ip", "cidr", "country"]

RULE_KINDS: tuple[str, ...] = ("allow", "deny")
MATCH_TYPES: tuple[str, ...] = ("ip", "cidr", "country")

_COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")


def normalize_value(match_type: str, value: str) -> tuple[str, int | None]:
    """Validate + canonicalize a rule value for its match type.

    Returns `(canonical_value, family)` where family is the IP version (4/6) for
    ip/cidr rules and None for country rules. Raises `ValueError` on bad input.
    """
    text = (value or "").strip()
    if not text:
        raise ValueError("value is required")
    if match_type == "country":
        if not _COUNTRY_RE.match(text):
            raise ValueError("country must be a 2-letter ISO 3166-1 alpha-2 code")
        return text.upper(), None
    if match_type == "ip":
        addr = ipaddress.ip_address(text)  # ValueError if malformed
        return str(addr), addr.version
    if match_type == "cidr":
        net = ipaddress.ip_network(text, strict=False)
        return str(net), net.version
    raise ValueError(f"unknown match_type '{match_type}'")


class IpRuleCreate(BaseModel):
    """Create an allow/deny rule. `value` is canonicalized in place."""

    kind: IpRuleKind
    match_type: IpMatchType
    value: str = Field(min_length=1)
    reason: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def _canonicalize_value(self) -> IpRuleCreate:
        self.value, _ = normalize_value(self.match_type, self.value)
        return self

    @property
    def family(self) -> int | None:
        return normalize_value(self.match_type, self.value)[1]


class IpRulePatch(BaseModel):
    """Toggle a rule or edit its reason — never its identity (kind/match_type/
    value); those define the rule, so a change is a new rule."""

    enabled: bool | None = None
    reason: str | None = None
