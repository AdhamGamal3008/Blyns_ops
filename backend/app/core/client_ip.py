"""Trusted-proxy-aware client-IP extraction (docs/IP_ACCESS_CONTROL_PLAN.md §2-E).

Both the rate limiter and the IP access filter make per-request decisions keyed on
the *client* IP. Behind a reverse proxy / load balancer, `request.client.host` is
the proxy's IP, and `X-Forwarded-For` (XFF) is attacker-controllable — anyone can
send `X-Forwarded-For: 1.2.3.4`. So XFF is trusted ONLY when the immediate peer
(the socket) is a configured trusted proxy; otherwise the socket IP is used and any
forwarded header is ignored. This prevents client-IP spoofing while still resolving
the real client when the deployment genuinely sits behind known proxies.

Stdlib `ipaddress` only — no dependency.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Sequence

from starlette.requests import Request

_Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_networks(entries: Sequence[str]) -> list[_Network]:
    """Parse trusted-proxy entries (single IPs or CIDRs, v4 or v6) into networks.
    Invalid entries are skipped rather than crashing config load."""
    nets: list[_Network] = []
    for entry in entries:
        text = (entry or "").strip()
        if not text:
            continue
        try:
            nets.append(ipaddress.ip_network(text, strict=False))
        except ValueError:
            continue
    return nets


def _ip_in_networks(ip: str, networks: Sequence[_Network]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr.version == net.version and addr in net for net in networks)


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def resolve_client_ip(
    socket_ip: str | None,
    forwarded_for: str | None,
    trusted_proxies: Sequence[str],
) -> str | None:
    """Resolve the real client IP.

    - If there are no trusted proxies, or the socket peer is not one of them,
      return the socket IP and ignore XFF entirely (untrusted, spoofable).
    - If the peer IS a trusted proxy, walk the XFF chain from the right, skipping
      trusted-proxy hops, and return the first non-trusted address — the client.
      If every hop is trusted (or XFF is absent/garbage), fall back to the
      leftmost valid entry, then to the socket IP.
    """
    if not socket_ip:
        return None
    networks = parse_networks(trusted_proxies)
    if not networks or not _ip_in_networks(socket_ip, networks):
        return socket_ip
    if not forwarded_for:
        return socket_ip

    chain = [part.strip() for part in forwarded_for.split(",") if part.strip()]
    for candidate in reversed(chain):
        if _valid_ip(candidate) and not _ip_in_networks(candidate, networks):
            return candidate
    for candidate in chain:
        if _valid_ip(candidate):
            return candidate
    return socket_ip


def client_ip(request: Request, trusted_proxies: Sequence[str]) -> str:
    """Request-scoped wrapper: the resolved client IP, or "unknown" when the
    peer address is unavailable (keeps callers key-able either way)."""
    socket_ip = request.client.host if request.client else None
    resolved = resolve_client_ip(
        socket_ip, request.headers.get("x-forwarded-for"), trusted_proxies
    )
    return resolved or "unknown"
