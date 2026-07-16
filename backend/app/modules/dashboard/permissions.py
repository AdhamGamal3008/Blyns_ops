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
]

# KPI → source module (a KPI is omitted unless the module is enabled AND the
# caller's role is ≥ READ on it).
KPI_SOURCES: dict[str, str] = {
    "open_projects": "projects",
    "overdue_tasks": "projects",
    "open_deals": "crm",
    "low_stock_items": "inventory",
    "unpaid_invoices_total": "finance",
}
