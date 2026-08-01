"""IP access rule value validation (docs/IP_ACCESS_CONTROL_PLAN.md §2-A): values
are validated + canonicalized at the edge, so a bad IP/CIDR/country is a 422."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.control_plane.ip_access.models import IpRuleCreate, normalize_value


def test_country_is_upper_cased_and_validated():
    rule = IpRuleCreate(kind="deny", match_type="country", value="kp")
    assert rule.value == "KP"
    assert rule.family is None
    with pytest.raises(ValidationError):
        IpRuleCreate(kind="deny", match_type="country", value="KOR")  # 3 letters


def test_ipv6_is_canonicalized_with_family():
    rule = IpRuleCreate(kind="allow", match_type="ip", value="2001:0DB8::0001")
    assert rule.value == "2001:db8::1"
    assert rule.family == 6


def test_ipv4_family():
    rule = IpRuleCreate(kind="deny", match_type="ip", value="198.51.100.7")
    assert rule.value == "198.51.100.7"
    assert rule.family == 4


def test_cidr_canonicalized_non_strict():
    rule = IpRuleCreate(kind="deny", match_type="cidr", value="10.0.0.5/8")
    assert rule.value == "10.0.0.0/8"  # host bits dropped
    assert rule.family == 4


def test_invalid_ip_and_cidr_rejected():
    with pytest.raises(ValidationError):
        IpRuleCreate(kind="deny", match_type="ip", value="not-an-ip")
    with pytest.raises(ValidationError):
        IpRuleCreate(kind="deny", match_type="cidr", value="10.0.0.0/999")


def test_normalize_value_helper():
    assert normalize_value("country", " us ") == ("US", None)
    assert normalize_value("cidr", "192.168.1.20/24") == ("192.168.1.0/24", 4)
