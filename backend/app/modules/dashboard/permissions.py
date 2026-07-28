"""Dashboard module RBAC surface (docs/modules/CLIENT_DASHBOARD.md).

RBAC resources: `dashboard` (plus `calendar`, `activity`). The quick-action
registry maps each shortcut to the module resource it needs WRITE on; the
server filters by the caller's role map + the company's enabled modules, so
the UI renders exactly what the user may do (§1, acceptance #1).
"""

from __future__ import annotations

from app.shared.enums import Level

RESOURCE = "dashboard"

QUICK_ACTIONS: list[dict] = [
    {
        "key": "project.new",
        "label": "New Project",
        "module": "projects",
        "required_level": int(Level.WRITE),
        "target_route": "/app/projects/new",
    },
    {
        "key": "crm.lead.new",
        "label": "New Lead",
        "module": "crm",
        "required_level": int(Level.WRITE),
        "target_route": "/app/crm/leads/new",
    },
    {
        "key": "inventory.adjust",
        "label": "Adjust Stock",
        "module": "inventory",
        "required_level": int(Level.WRITE),
        "target_route": "/app/inventory/adjust",
    },
    {
        "key": "finance.invoice.new",
        "label": "New Invoice",
        "module": "finance",
        "required_level": int(Level.WRITE),
        "target_route": "/app/finance/invoices/new",
    },
    {
        "key": "employee.invite",
        "label": "Invite Employee",
        "module": "settings",
        "required_level": int(Level.WRITE),
        "target_route": "/app/settings/employees",
    },
    # Secondary shortcuts (declared after the primaries so a cold-start user's
    # inline set stays today's curated five; behavior ranking promotes these).
    {
        "key": "crm.deal.new",
        "label": "New Deal",
        "module": "crm",
        "required_level": int(Level.WRITE),
        "target_route": "/app/crm/deals/new",
    },
    {
        "key": "crm.contact.new",
        "label": "New Contact",
        "module": "crm",
        "required_level": int(Level.WRITE),
        "target_route": "/app/crm/contacts/new",
    },
    {
        "key": "finance.bill.new",
        "label": "New Bill",
        "module": "finance",
        "required_level": int(Level.WRITE),
        "target_route": "/app/finance/bills/new",
    },
    {
        "key": "inventory.product.new",
        "label": "New Product",
        "module": "inventory",
        "required_level": int(Level.WRITE),
        "target_route": "/app/inventory/products/new",
    },
]

# Quick-action key → the activity_log `action` strings that count as "did
# exactly this" (docs/QUICK_ACTIONS_PERSONALIZATION_PLAN.md §3). Confirmed
# against the write_activity/_log calls in each owning module's service.py.
# Keep this in step with QUICK_ACTIONS: a missing entry is not fatal — the
# module-engagement term still ranks the action, just less sharply.
EXACT_ACTIONS: dict[str, frozenset[str]] = {
    "project.new": frozenset({"project.created"}),
    "crm.lead.new": frozenset({"crm.lead.created"}),
    "crm.deal.new": frozenset({"crm.deal.created"}),
    "crm.contact.new": frozenset({"crm.contact.created"}),
    "inventory.adjust": frozenset({
        "inventory.receipt", "inventory.issue",
        "inventory.adjustment", "inventory.transfer",
    }),
    "inventory.product.new": frozenset({"inventory.product.created"}),
    "finance.invoice.new": frozenset({"finance.invoice.created", "finance.invoice.sent"}),
    "finance.bill.new": frozenset({"finance.bill.created", "finance.bill.sent"}),
    "employee.invite": frozenset({"settings.employee.created"}),
}

# KPI → source module (a KPI is omitted unless the module is enabled AND the
# caller's role is ≥ READ on it).
KPI_SOURCES: dict[str, str] = {
    "open_projects": "projects",
    "overdue_tasks": "projects",
    "open_deals": "crm",
    "low_stock_items": "inventory",
    "unpaid_invoices_total": "finance",
}
