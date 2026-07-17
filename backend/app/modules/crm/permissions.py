"""CRM module RBAC surface + pipeline definition (docs/modules/CRM.md).

RBAC resource: `crm` — READ for GET, WRITE for mutations (§3). The stage order
lives here (not in seed.py) because the service enforces rules over it; the
seeded `default` pipeline doc carries the same list for tenants to read.
"""

from __future__ import annotations

RESOURCE = "crm"

# Ordered pipeline stages (§2). `won`/`lost` are terminal.
STAGES: list[str] = ["new", "qualified", "proposal", "negotiation", "won", "lost"]
TERMINAL_STAGES: frozenset[str] = frozenset({"won", "lost"})
OPEN_STAGES: list[str] = [s for s in STAGES if s not in TERMINAL_STAGES]

ACCOUNT_STATUSES: list[str] = ["prospect", "customer", "inactive"]
LEAD_STATUSES: list[str] = ["new", "contacted", "qualified", "unqualified", "converted"]
ACTIVITY_TYPES: list[str] = ["call", "email", "meeting", "note", "task"]
ENTITY_TYPES: list[str] = ["account", "contact", "lead", "deal"]
