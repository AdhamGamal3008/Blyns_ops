"""Trusted-proxy-aware client-IP extraction (docs/IP_ACCESS_CONTROL_PLAN.md §2-E):
XFF is honoured only when the socket peer is a configured trusted proxy, so a
forwarded header can never spoof the client IP."""

from __future__ import annotations

from app.core.client_ip import resolve_client_ip


def test_no_trusted_proxies_uses_socket_and_ignores_xff():
    assert resolve_client_ip("203.0.113.9", "1.2.3.4", []) == "203.0.113.9"


def test_untrusted_peer_ignores_forwarded_header():
    # the peer is not a trusted proxy → XFF is spoofable and must be ignored
    assert resolve_client_ip("203.0.113.9", "1.2.3.4", ["10.0.0.0/8"]) == "203.0.113.9"


def test_trusted_proxy_returns_client_from_xff():
    assert resolve_client_ip("10.0.0.5", "198.51.100.7", ["10.0.0.0/8"]) == "198.51.100.7"


def test_trusted_proxy_walks_chain_right_to_left():
    # XFF: client, edge-proxy, inner-proxy; the peer is the inner proxy (trusted)
    ip = resolve_client_ip(
        "10.0.0.5", "198.51.100.7, 10.0.0.9, 10.0.0.5", ["10.0.0.0/8"]
    )
    assert ip == "198.51.100.7"


def test_trusted_proxy_as_single_ip_not_cidr():
    assert resolve_client_ip("192.0.2.1", "203.0.113.5", ["192.0.2.1"]) == "203.0.113.5"


def test_all_hops_trusted_falls_back_to_leftmost():
    assert resolve_client_ip("10.0.0.5", "10.0.0.1, 10.0.0.2", ["10.0.0.0/8"]) == "10.0.0.1"


def test_garbage_xff_falls_back_to_socket():
    assert resolve_client_ip("10.0.0.5", "not-an-ip, also-bad", ["10.0.0.0/8"]) == "10.0.0.5"


def test_ipv6_socket_and_trusted_proxy():
    assert resolve_client_ip("2001:db8::1", None, []) == "2001:db8::1"
    # a trusted v6 proxy forwards a client that sits OUTSIDE the trusted range
    ip = resolve_client_ip("2001:db8::1", "2001:db9::9", ["2001:db8::/32"])
    assert ip == "2001:db9::9"


def test_missing_socket_returns_none():
    assert resolve_client_ip(None, "1.2.3.4", []) is None
