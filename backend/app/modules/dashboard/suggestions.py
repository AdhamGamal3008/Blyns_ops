"""Dashboard "next step" suggestion rules (docs/QUICK_ACTIONS_PERSONALIZATION_PLAN.md
Phase 3).

A small, declarative, in-house rule registry — no AI. Each rule reads one cheap
data-state count (reusing the KPI queries where they already exist) and, when the
count is non-zero, yields a suggestion with a human message and a deep-link CTA.
The service gates rules by the caller's role + enabled modules, applies the
user's dismissals, and caps the strip; rules themselves know nothing about that.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.dashboard import repository as repo
from app.shared.enums import Level


@dataclass(frozen=True)
class Suggestion:
    key: str
    message: str
    cta_label: str
    target_route: str
    priority: int
    # "how much" the condition weighs right now — bookkeeping for dismissal
    # re-show (a dismissed suggestion returns once its signal grows). Not exposed.
    signal: int


@dataclass(frozen=True)
class Rule:
    key: str
    module: str
    required_level: Level
    priority: int
    cta_label: str
    target_route: str
    count: Callable[[AsyncIOMotorDatabase], Awaitable[int]]
    message: Callable[[int], str]


def _n(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


# Higher priority shows first; every rule needs WRITE on its module, since each
# suggestion is a thing to *do*, not merely to look at.
RULES: list[Rule] = [
    Rule(
        key="projects.overdue",
        module="projects",
        required_level=Level.WRITE,
        priority=100,
        cta_label="Review projects",
        target_route="/app/projects",
        count=repo.kpi_overdue_tasks,
        message=lambda n: f"{_n(n, 'milestone is', 'milestones are')} overdue.",
    ),
    Rule(
        key="inventory.low_stock",
        module="inventory",
        required_level=Level.WRITE,
        priority=90,
        cta_label="Adjust stock",
        target_route="/app/inventory/low",
        count=repo.kpi_low_stock_items,
        message=lambda n: f"{_n(n, 'product is', 'products are')} low on stock.",
    ),
    Rule(
        key="finance.draft_invoices",
        module="finance",
        required_level=Level.WRITE,
        priority=80,
        cta_label="Review drafts",
        target_route="/app/finance/invoices",
        count=repo.count_draft_invoices,
        message=lambda n: f"{_n(n, 'draft invoice is', 'draft invoices are')} waiting to be sent.",
    ),
    Rule(
        key="crm.new_leads",
        module="crm",
        required_level=Level.WRITE,
        priority=70,
        cta_label="Work leads",
        target_route="/app/crm/leads",
        count=repo.count_new_leads,
        message=lambda n: f"{_n(n, 'new lead needs', 'new leads need')} following up.",
    ),
    Rule(
        key="finance.unpaid_invoices",
        module="finance",
        required_level=Level.WRITE,
        priority=60,
        cta_label="Chase payments",
        target_route="/app/finance/invoices",
        count=repo.count_unpaid_invoices,
        message=lambda n: f"{_n(n, 'invoice is', 'invoices are')} awaiting payment.",
    ),
]

SUGGESTION_KEYS: frozenset[str] = frozenset(r.key for r in RULES)
