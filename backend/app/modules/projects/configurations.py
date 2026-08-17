"""Tenant-defined project configurations (docs/PROJECT_CONFIGURATIONS_PLAN.md §5).

A configuration is a named, versioned set of the 9 stages' entry documents,
quality gates and thresholds, plus the workflow shape. Two rules shape everything
here:

* **Versions are immutable (D1).** Editing never mutates a published version; it
  publishes a new one and advances `current_version`. Projects pin the version
  current at their creation, so a running project can never have its stages or
  gates move under it. There is no server-side draft — a publish carries the full
  edited set (§3 "publish-from-payload").
* **The 9-stage skeleton is fixed (D2).** Stage keys, orders, approver positions
  and module integrations are not editable, which is what keeps the Production /
  Finance / Inventory key-hooks working (G-2). Only a stage's documents, its
  quality gates and their thresholds vary per configuration.

Managing configurations is `settings` WRITE (the same guard as the approver map,
which is the closest existing analog); reading them for the Stage-1 picker is
`projects` READ. Every mutation is audited.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from bson import ObjectId
from pymongo.errors import BulkWriteError, DuplicateKeyError

from app.core.audit import write_activity
from app.core.errors import TENANT_NOT_FOUND, VALIDATION_ERROR, DomainError
from app.modules.projects import repository as repo
from app.modules.projects import seed as projects_seed
from app.modules.projects.models import (
    ConfigurationVersionPublish,
    GateCatalogCreate,
    ProjectConfigurationCreate,
    ProjectConfigurationPatch,
)
from app.tenant.deps import ClientPrincipal

# Fields a version copy must never carry over — they identify the SOURCE doc.
_NOT_COPIED = ("_id", "configuration_id", "config_version")


def _oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception as exc:
        raise DomainError(TENANT_NOT_FOUND, "Configuration not found.", 404) from exc


async def _log(
    principal: ClientPrincipal, action: str, config: dict, details: dict | None = None
) -> None:
    await write_activity(
        principal.tenant_db,
        actor_id=str(principal.user["_id"]),
        action=action,
        entity={"type": "project_configuration", "id": str(config["_id"]),
                "label": config["name"]},
        details=details or {},
        actor_name=principal.user["name"],
        module="projects",
    )


async def _require_config(principal: ClientPrincipal, config_id: str) -> dict:
    config = await repo.project_config(principal.tenant_db, _oid(config_id))
    if config is None:
        raise DomainError(TENANT_NOT_FOUND, "Configuration not found.", 404)
    return config


def _copy_into(doc: dict, config_id: ObjectId, version: int) -> dict:
    """One definition doc re-homed into a (configuration, version)."""
    copied = {k: v for k, v in doc.items() if k not in _NOT_COPIED}
    copied["configuration_id"] = config_id
    copied["config_version"] = version
    return copied


async def _write_version(
    db: Any, config_id: ObjectId, version: int,
    stages: list[dict], gates: list[dict],
) -> None:
    """Insert a complete version — its 9 stage docs and its own gate-rule copies.
    Nothing existing is touched, which is what makes a version immutable."""
    if stages:
        await db[repo.STAGE_DEFS].insert_many(
            [_copy_into(s, config_id, version) for s in stages]
        )
    if gates:
        await db[repo.GATE_RULES].insert_many(
            [_copy_into(g, config_id, version) for g in gates]
        )


# --- reading ------------------------------------------------------------------

async def list_configurations(
    principal: ClientPrincipal, active_only: bool = False
) -> list[dict]:
    """The Stage-1 picker's list (`projects` READ) — and the Settings list, which
    also wants deactivated ones."""
    return await repo.project_configs(principal.tenant_db, active_only=active_only)


async def get_configuration(principal: ClientPrincipal, config_id: str) -> dict:
    """A configuration's CURRENT version in full — what the editor loads."""
    db = principal.tenant_db
    config = await _require_config(principal, config_id)
    scope = repo.scope_of(config)
    return {
        **config,
        "stages": await repo.stage_defs(db, scope),
        "gates": await repo.gate_rules(db, scope),
    }


# --- create by cloning --------------------------------------------------------

async def create_configuration(
    principal: ClientPrincipal, payload: ProjectConfigurationCreate
) -> dict:
    """§5 — a configuration is always created by CLONING an existing one, so a
    tenant starts from a working 9-stage machine rather than an empty one."""
    db = principal.tenant_db
    base = (
        await _require_config(principal, payload.base_configuration_id)
        if payload.base_configuration_id
        else await repo.default_project_config(db)
    )
    if base is None:
        raise DomainError(
            VALIDATION_ERROR,
            "This workspace has no project configuration to clone from — re-seed "
            "the Projects module (scripts/migrate_projects_v4.py).",
            409,
        )

    base_scope = repo.scope_of(base)
    stages = await repo.stage_defs(db, base_scope)
    gates = await repo.gate_rules(db, base_scope)

    config = await repo.insert(db, repo.PROJECT_CONFIGS, {
        "name": payload.name,
        "description": payload.description or f"Cloned from {base['name']}.",
        "workflow_shape": base.get("workflow_shape", "sequential"),
        "current_version": 1,
        "is_system": False,
        "is_default": False,
        "is_active": True,
        "cloned_from": base["_id"],
        "created_by": str(principal.user["_id"]),
    })
    await _write_version(db, config["_id"], 1, stages, gates)

    await _log(principal, "projects.configuration_created", config,
               {"cloned_from": base["name"], "stages": len(stages),
                "gates": len(gates)})
    return config


# --- rename / default / activate ----------------------------------------------

async def patch_configuration(
    principal: ClientPrincipal, config_id: str, patch: ProjectConfigurationPatch
) -> dict:
    """Rename, set the default, or activate/deactivate. G-4's invariants — exactly
    one default, at least one active config, system configs are never deleted —
    are enforced here."""
    db = principal.tenant_db
    config = await _require_config(principal, config_id)
    fields = patch.model_dump(exclude_unset=True)

    if fields.get("is_default") is True:
        # exactly one default: demote whoever holds it
        await db[repo.PROJECT_CONFIGS].update_many(
            {"_id": {"$ne": config["_id"]}, "is_default": True},
            {"$set": {"is_default": False}},
        )
        fields["is_active"] = True  # the default must be usable
    elif fields.get("is_default") is False and config.get("is_default"):
        raise DomainError(
            VALIDATION_ERROR,
            "A workspace must always have a default configuration — set another "
            "one as default instead of clearing this one.",
            422,
        )

    if fields.get("is_active") is False:
        if config.get("is_default"):
            raise DomainError(
                VALIDATION_ERROR,
                "The default configuration cannot be deactivated — make another "
                "configuration the default first.",
                422,
            )
        if await repo.active_config_count(db) <= 1:
            raise DomainError(
                VALIDATION_ERROR,
                "At least one project configuration must stay active.",
                422,
            )

    fields = {k: v for k, v in fields.items() if v is not None}
    if not fields:
        return config
    fields["updated_by"] = str(principal.user["_id"])
    updated = await repo.update(db, repo.PROJECT_CONFIGS, config["_id"], fields)
    assert updated is not None

    await _log(principal, "projects.configuration_updated", updated,
               {"fields": [k for k in fields if k != "updated_by"]})
    return updated


async def delete_configuration(principal: ClientPrincipal, config_id: str) -> None:
    """Non-system only, and never while a live project pins it — deleting a pinned
    configuration would strand that project's stage machine (G-4)."""
    db = principal.tenant_db
    config = await _require_config(principal, config_id)

    if config.get("is_system"):
        raise DomainError(
            VALIDATION_ERROR,
            f"'{config['name']}' is a built-in configuration and cannot be deleted.",
            422,
        )
    if config.get("is_default"):
        raise DomainError(
            VALIDATION_ERROR,
            "The default configuration cannot be deleted — make another "
            "configuration the default first.",
            422,
        )
    pinned = await repo.projects_on_config(db, config["_id"])
    if pinned:
        raise DomainError(
            VALIDATION_ERROR,
            f"{pinned} project(s) run on '{config['name']}' — deactivate it "
            "instead so existing projects keep working.",
            422,
        )

    await repo.soft_delete(
        db, repo.PROJECT_CONFIGS, config["_id"], str(principal.user["_id"])
    )
    await _log(principal, "projects.configuration_deleted", config)


# --- publishing a version ------------------------------------------------------

def _rebuild_dependencies(stages: list[dict], shape: str) -> list[dict]:
    """Dependency entry-gates encode the workflow SHAPE, not tenant choices, so
    they are re-derived only when the shape actually changes — the seeded
    sequential chain uses semantic gate keys (`design_frozen`, `goods_released`)
    that cannot be regenerated, so an unchanged shape carries them over as-is."""
    if shape != "concurrent":
        return stages
    return projects_seed.concurrent_variant(stages)


def _apply_stage_edits(
    stage: dict, spec: Any, catalog: dict[str, dict]
) -> dict:
    """Overlay one stage's editable surface (D2): its entry documents and which
    catalog gates hang off it. Everything else — order, name, approver position,
    automated tasks, recovery, release checklist — is carried over untouched."""
    edited = deepcopy(stage)
    dependencies = [
        g for g in (stage.get("entry_gates") or []) if g.get("type") == "dependency"
    ]
    documents = [
        {
            "key": doc.key,
            "type": "document",
            "label": doc.label or projects_seed.gate_label(doc.key),
            "blocking": doc.blocking,
        }
        for doc in spec.entry_documents
    ]
    edited["entry_gates"] = documents + dependencies
    edited["quality_gates"] = [k for k in spec.quality_gates if k in catalog]
    return edited


async def publish_version(
    principal: ClientPrincipal, config_id: str, payload: ConfigurationVersionPublish
) -> dict:
    """§5 — publish the full edited set as an immutable new version.

    The previous version is left exactly as it was, so every project pinned to it
    keeps running against the machine it started on (D1). Only projects created
    AFTER this call pick the new version up.
    """
    db = principal.tenant_db
    config = await _require_config(principal, config_id)
    scope = repo.scope_of(config)
    assert scope.config_version is not None
    version = max(
        scope.config_version, await repo.highest_config_version(db, config["_id"])
    ) + 1
    shape = payload.workflow_shape or config.get("workflow_shape", "sequential")

    catalog = {g["key"]: g for g in await repo.gate_catalog(db)}
    current = {s["key"]: s for s in await repo.stage_defs(db, scope)}
    if not current:
        raise DomainError(
            VALIDATION_ERROR,
            f"'{config['name']}' has no stages to publish from.",
            409,
        )

    unknown_stages = [s.key for s in payload.stages if s.key not in current]
    if unknown_stages:
        raise DomainError(
            VALIDATION_ERROR,
            f"Unknown stage(s): {', '.join(sorted(unknown_stages))}. The 9-stage "
            "skeleton is fixed — a configuration tunes its stages, it cannot add "
            "or remove them.",
            422,
        )
    unknown_gates = {
        key for s in payload.stages for key in s.quality_gates if key not in catalog
    }
    if unknown_gates:
        raise DomainError(
            VALIDATION_ERROR,
            f"Unknown quality gate(s): {', '.join(sorted(unknown_gates))}. Add them "
            "to the gate catalog first.",
            422,
        )

    # stages the payload did not mention are carried over unchanged
    edits = {s.key: s for s in payload.stages}
    stages = [
        _apply_stage_edits(definition, edits[key], catalog) if key in edits
        else deepcopy(definition)
        for key, definition in current.items()
    ]
    if shape != config.get("workflow_shape", "sequential"):
        stages = _rebuild_dependencies(stages, shape)
    for stage in stages:
        stage["workflow_type"] = shape

    # Gate rules: one COPY per gate this version actually attaches, taken from the
    # catalog definition and tuned by the payload (G-3 — never a shared doc, and
    # never a write-back to the catalog).
    tuning = {g.key: g for g in payload.gates}
    attached = {key for stage in stages for key in (stage.get("quality_gates") or [])}
    gates: list[dict] = []
    for key in sorted(attached):
        rule = {k: v for k, v in catalog[key].items()
                if k not in ("_id", "is_builtin", "is_deleted", "name")}
        tuned = tuning.get(key)
        if tuned is not None:
            for field in ("threshold", "severe_threshold", "blocking", "checklist"):
                value = getattr(tuned, field)
                if value is not None:
                    rule[field] = value
        gates.append(rule)

    try:
        await _write_version(db, config["_id"], version, stages, gates)
    # insert_many reports a duplicate key as BulkWriteError, NOT DuplicateKeyError —
    # they are siblings, so catching only the latter would let this escape as a 500.
    except (BulkWriteError, DuplicateKeyError) as exc:
        # Two publishes raced: both read the same current_version, and the compound
        # unique index caught the loser. Nothing of theirs was adopted — the config
        # still points at the winner's version — so ask them to reload and redo it
        # rather than silently overwriting what the winner just published.
        raise DomainError(
            VALIDATION_ERROR,
            f"'{config['name']}' was published by someone else a moment ago — "
            "reload the configuration and re-apply your changes.",
            409,
        ) from exc

    updated = await repo.update(db, repo.PROJECT_CONFIGS, config["_id"], {
        "current_version": version,
        "workflow_shape": shape,
        "updated_by": str(principal.user["_id"]),
    })
    assert updated is not None

    await _log(principal, "projects.configuration_published", updated,
               {"version": version, "shape": shape,
                "stages": len(stages), "gates": len(gates)})
    return updated


# --- gate catalog --------------------------------------------------------------

async def list_gate_catalog(principal: ClientPrincipal) -> list[dict]:
    return await repo.gate_catalog(principal.tenant_db)


async def create_gate_catalog_entry(
    principal: ClientPrincipal, payload: GateCatalogCreate
) -> dict:
    """A tenant's own gate definition. Attaching it to a stage copies it into that
    config-version's gate rules; this entry is the reusable template (G-3)."""
    db = principal.tenant_db
    if await repo.gate_catalog_entry(db, payload.key) is not None:
        raise DomainError(
            VALIDATION_ERROR, f"A gate named '{payload.key}' already exists.", 422
        )
    try:
        doc = await repo.insert(db, repo.GATE_CATALOG, {
            **payload.model_dump(),
            "is_builtin": False,
            "created_by": str(principal.user["_id"]),
        })
    except DuplicateKeyError as exc:
        # The check above is not atomic; the unique index is the real arbiter.
        raise DomainError(
            VALIDATION_ERROR, f"A gate named '{payload.key}' already exists.", 422
        ) from exc
    await write_activity(
        db,
        actor_id=str(principal.user["_id"]),
        action="projects.gate_catalog_created",
        entity={"type": "gate_catalog", "id": payload.key, "label": payload.name},
        details={"type": payload.type},
        actor_name=principal.user["name"],
        module="projects",
    )
    return doc


async def delete_gate_catalog_entry(principal: ClientPrincipal, key: str) -> None:
    """Custom gates only — the 8 built-ins are part of the seeded machine.

    Removing a catalog entry does NOT touch the tuned copies already published
    into configuration versions; those keep working, which is the whole point of
    copy-on-attach (G-3).
    """
    db = principal.tenant_db
    entry = await repo.gate_catalog_entry(db, key)
    if entry is None:
        raise DomainError(TENANT_NOT_FOUND, f"Gate '{key}' is not defined.", 404)
    if entry.get("is_builtin"):
        raise DomainError(
            VALIDATION_ERROR,
            f"'{entry.get('name', key)}' is a built-in gate and cannot be deleted.",
            422,
        )
    await repo.soft_delete(
        db, repo.GATE_CATALOG, entry["_id"], str(principal.user["_id"])
    )
    await write_activity(
        db,
        actor_id=str(principal.user["_id"]),
        action="projects.gate_catalog_deleted",
        entity={"type": "gate_catalog", "id": key,
                "label": entry.get("name", key)},
        details={},
        actor_name=principal.user["name"],
        module="projects",
    )
