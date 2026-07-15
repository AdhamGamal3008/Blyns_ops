"""Shared enums (docs/AUTH_RBAC.md §2)."""

from __future__ import annotations

from enum import IntEnum


class Level(IntEnum):
    """4-level ordered permission enum, applied per resource.

    A role is a map of resource -> Level; the RBAC guard is a `>=` check.
    """

    NONE = 0   # cannot view; resource hidden
    VIEW = 1   # can see it exists (listing/labels) but not open details
    READ = 2   # view + read full details
    WRITE = 3  # view + read + create/update/delete
