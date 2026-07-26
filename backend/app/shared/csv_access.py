"""Per-entity CSV access control (docs/modules/SETTINGS.md §1.3, CRM/INVENTORY §7).

Import/export is gated by a permission dimension separate from the module Level
map: a role names *which tabs* it may **export**, **import**, and
**approve_import**, each as a list of `"{module}:{entity}"` keys. The three
capabilities are independent grants a Settings admin hands out per tab.

Rules (settled with the owner):

* **Layered on module READ.** A grant only takes effect if the holder also has
  at least READ on that module — nobody pulls or pushes a module's data via CSV
  that they cannot otherwise see.
* **Approve implies import.** Holding `approve_import` for a tab lets you import
  it directly, and your own imports commit with no second sign-off. So a
  non-approver's import is *staged for approval*; an approver's commits at once.
* **Rollout: only the Owner is grandfathered.** A role with no explicit
  `csv_access` yet is treated as full grants **iff** it is Owner-equivalent
  (WRITE on every resource); every other such role has no CSV access until an
  admin grants it. Once a role's access is edited it is stored explicitly and
  this default no longer applies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.modules.settings.seed import CLIENT_RESOURCES
from app.shared.enums import Level

if TYPE_CHECKING:
    from app.tenant.deps import ClientPrincipal

CAPABILITIES = ("export", "import", "approve_import")

# Modules that expose CSV entities. Kept here (not derived) so this module does
# not import the module routers; the catalog reads each module's spec registry.
_CSV_MODULES = ("crm", "inventory")


def _registry(module: str) -> dict[str, Any]:
    """The module's CsvEntity registry, imported lazily so a shared module never
    hard-depends on a feature module at import time."""
    if module == "crm":
        from app.modules.crm.csv_schema import ENTITIES
        return ENTITIES
    if module == "inventory":
        from app.modules.inventory.csv_schema import ENTITIES
        return ENTITIES
    return {}


def entity_key(module: str, entity: str) -> str:
    return f"{module}:{entity}"


def catalog() -> list[dict[str, Any]]:
    """Every CSV tab across every module, for the role editor's multi-selects and
    for grant validation. `importable=False` (a derived view like stock levels)
    can be exported and approved-never; it is offered only under Export."""
    out: list[dict[str, Any]] = []
    for module in _CSV_MODULES:
        for name, spec in _registry(module).items():
            out.append({
                "key": entity_key(module, name),
                "module": module,
                "entity": name,
                "label": f"{module.title()} · {spec.label}",
                "importable": spec.can_import,
            })
    return out


def _keys(*, importable_only: bool) -> set[str]:
    return {
        e["key"] for e in catalog()
        if e["importable"] or not importable_only
    }


def exportable_keys() -> set[str]:
    return _keys(importable_only=False)


def importable_keys() -> set[str]:
    return _keys(importable_only=True)


def _empty() -> dict[str, list[str]]:
    return {cap: [] for cap in CAPABILITIES}


def _full() -> dict[str, list[str]]:
    return {
        "export": sorted(exportable_keys()),
        "import": sorted(importable_keys()),
        "approve_import": sorted(importable_keys()),
    }


def _is_owner_equivalent(role: dict) -> bool:
    """WRITE on every client resource — the seeded Owner, and any role an admin
    has raised to the same. Only these are grandfathered into full CSV access."""
    perms = role.get("permissions", {})
    return all(int(perms.get(res, 0)) >= int(Level.WRITE) for res in CLIENT_RESOURCES)


def effective(role: dict) -> dict[str, list[str]]:
    """A role's CSV grants: the explicit `csv_access` if set, else the rollout
    default (full for an Owner-equivalent role, empty otherwise)."""
    stored = role.get("csv_access")
    if isinstance(stored, dict):
        return {cap: list(stored.get(cap) or []) for cap in CAPABILITIES}
    return _full() if _is_owner_equivalent(role) else _empty()


# --- guards ------------------------------------------------------------------

def _has_module_read(principal: ClientPrincipal, module: str) -> bool:
    return principal.level_for(module) >= Level.READ


def can_export(principal: ClientPrincipal, module: str, entity: str) -> bool:
    if not _has_module_read(principal, module):
        return False
    return entity_key(module, entity) in effective(principal.role)["export"]


def can_approve(principal: ClientPrincipal, module: str, entity: str) -> bool:
    if not _has_module_read(principal, module):
        return False
    return entity_key(module, entity) in effective(principal.role)["approve_import"]


def can_import(principal: ClientPrincipal, module: str, entity: str) -> bool:
    """Import grant OR approve grant — approve implies import."""
    if not _has_module_read(principal, module):
        return False
    access = effective(principal.role)
    key = entity_key(module, entity)
    return key in access["import"] or key in access["approve_import"]


def needs_approval(principal: ClientPrincipal, module: str, entity: str) -> bool:
    """A holder who may import but may not approve: their commit is staged for
    someone with approve rights (unless they are that someone)."""
    return can_import(principal, module, entity) and not can_approve(
        principal, module, entity
    )


# --- validation (role editor) ------------------------------------------------

def validate(access: Any) -> dict[str, list[str]]:
    """Normalise and check a `csv_access` payload from the role editor.

    Export keys must name an exportable tab; import and approve_import keys must
    name an *importable* one (a derived view like stock levels can never be
    imported, so granting its import is a mistake worth refusing loudly)."""
    from app.core.errors import VALIDATION_ERROR, DomainError

    if access is None:
        return _empty()
    if not isinstance(access, dict):
        raise DomainError(VALIDATION_ERROR, "csv_access must be an object.", 422)

    unknown_caps = set(access) - set(CAPABILITIES)
    if unknown_caps:
        raise DomainError(
            VALIDATION_ERROR,
            f"Unknown CSV capabilities: {sorted(unknown_caps)}.", 422,
        )

    allowed = {
        "export": exportable_keys(),
        "import": importable_keys(),
        "approve_import": importable_keys(),
    }
    clean: dict[str, list[str]] = {}
    for cap in CAPABILITIES:
        raw = access.get(cap) or []
        if not isinstance(raw, list):
            raise DomainError(VALIDATION_ERROR, f"csv_access.{cap} must be a list.", 422)
        keys = {str(k) for k in raw}
        bad = keys - allowed[cap]
        if bad:
            raise DomainError(
                VALIDATION_ERROR,
                f"csv_access.{cap} names tabs that cannot be {cap.replace('_', ' ')}"
                f"ed: {sorted(bad)}.",
                http_status=422,
            )
        # store in catalog order, so two equal grants compare equal
        clean[cap] = [e["key"] for e in catalog() if e["key"] in keys]
    return clean
