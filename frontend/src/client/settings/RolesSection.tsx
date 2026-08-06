// Client roles RBAC editor (§1.3): every resource gets a 4-way selector
// (None / View / Read / Write) — the role editor contract.

import { Plus, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import type { CsvAccess, CsvCatalogEntry } from "../../shared/types";
import {
  Badge,
  Banner,
  Button,
  CardHeader,
  Checkbox,
  DataState,
  errorText,
  Field,
  FormModal,
  Input,
  Popover,
  Row,
  Stack,
} from "../../shared/ui";
import { CLIENT_RESOURCES, LevelChip, resourceLabel, RoleMatrix } from "./RoleMatrix";
import styles from "./RolesSection.module.css";

interface Role {
  id: string;
  name: string;
  permissions: Record<string, number>;
  is_system?: boolean;
  csv_access?: CsvAccess;
}

export function RolesSection(props: { canWrite: boolean }) {
  const [roles, setRoles] = useState<Role[] | null>(null);
  const [editing, setEditing] = useState<Role | "new" | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<Role[]>("/settings/roles").then((r) => setRoles(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  async function remove(role: Role) {
    if (!window.confirm(`Delete role "${role.name}"?`)) return;
    setError(null);
    try {
      await api(`/settings/roles/${role.id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section>
      <CardHeader
        title="Client roles"
        description="Who can reach which module, and how far in."
        actions={
          props.canWrite && (
            <Button size="compact" onClick={() => setEditing("new")}>
              <Plus size={15} aria-hidden="true" />
              New role
            </Button>
          )
        }
      />

      {error != null && roles != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!roles && !error}
        error={roles ? null : error}
        onRetry={load}
        isEmpty={roles?.length === 0}
        emptyTitle="No roles yet"
      >
        {/* Roles × resources: one glance shows how the grants differ. */}
        <div className={styles.scroll}>
          <table className={styles.overview}>
            <thead>
              <tr>
                <th scope="col" className={styles.roleHead}>Role</th>
                {CLIENT_RESOURCES.map((r) => (
                  <th key={r} scope="col" className={styles.resHead}>{resourceLabel(r)}</th>
                ))}
                {props.canWrite && (
                  <th scope="col" className={styles.actionHead}>
                    <span className={styles.srOnly}>Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {(roles ?? []).map((role) => (
                <tr key={role.id}>
                  <th scope="row" className={styles.roleCell}>
                    <Row gap={2} className={styles.noWrap}>
                      <span className={styles.roleName}>{role.name}</span>
                      {role.is_system && <Badge tone="neutral">seeded</Badge>}
                    </Row>
                  </th>
                  {CLIENT_RESOURCES.map((r) => (
                    // data-label carries the column name into the mobile card layout
                    <td key={r} className={styles.levelCell} data-label={resourceLabel(r)}>
                      <LevelChip level={role.permissions[r] ?? 0} />
                    </td>
                  ))}
                  {props.canWrite && (
                    <td className={styles.actionCell}>
                      <Row gap={2} className={styles.noWrap}>
                        <Button variant="ghost" size="compact" onClick={() => setEditing(role)}>
                          Edit
                        </Button>
                        <Button variant="ghost" size="compact" onClick={() => remove(role)}>
                          Delete
                        </Button>
                      </Row>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </DataState>

      {editing && (
        <RoleEditor
          role={editing === "new" ? null : editing}
          onDone={() => { setEditing(null); load(); }}
        />
      )}
    </section>
  );
}

export function RoleEditor(props: { role: Role | null; onDone: () => void }) {
  const [name, setName] = useState(props.role?.name ?? "");
  const [perms, setPerms] = useState<Record<string, number>>(
    () => Object.fromEntries(
      CLIENT_RESOURCES.map((r) => [r, props.role?.permissions[r] ?? 0]),
    ),
  );
  const [csvAccess, setCsvAccess] = useState<CsvAccess>(() => ({
    export: props.role?.csv_access?.export ?? [],
    import: props.role?.csv_access?.import ?? [],
    approve_import: props.role?.csv_access?.approve_import ?? [],
  }));
  const [catalog, setCatalog] = useState<CsvCatalogEntry[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<CsvCatalogEntry[]>("/settings/csv-catalog")
      .then((r) => setCatalog(r.data))
      .catch(() => setCatalog([])); // grants just won't be editable if this fails
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const body = { name, permissions: perms, csv_access: csvAccess };
    try {
      if (props.role) {
        await api(`/settings/roles/${props.role.id}`, { method: "PATCH", body });
      } else {
        await api("/settings/roles", { method: "POST", body });
      }
      props.onDone();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  const granted = CLIENT_RESOURCES.filter((r) => (perms[r] ?? 0) > 0).length;

  return (
    <FormModal
      open
      onOpenChange={(o) => !o && props.onDone()}
      size="lg"
      title={props.role ? `Edit role: ${props.role.name}` : "New role"}
      description={
        <span className={styles.grantCount}>
          <ShieldCheck size={14} aria-hidden="true" />
          {granted} of {CLIENT_RESOURCES.length} resources granted
        </span>
      }
      onSubmit={submit}
      error={error}
      errorTitle="Could not save the role"
      busy={busy}
      submitLabel="Save role"
    >
      <Stack gap={5}>
        <Field label="Role name" required>
          <Input value={name} onChange={(e) => setName(e.target.value)} required
            placeholder="e.g. Estimator" />
        </Field>
        <RoleMatrix value={perms} onChange={setPerms} />
        {catalog.length > 0 && (
          <CsvAccessEditor catalog={catalog} value={csvAccess} onChange={setCsvAccess} />
        )}
      </Stack>
    </FormModal>
  );
}

// --- CSV grant multi-selects (SETTINGS.md §1.3) ------------------------------

/** Three tab pickers — export / import / approve — populated from the catalog.
 *  Export offers every tab; import and approve offer only the importable ones (a
 *  derived, export-only view can never be imported, so it is never on offer). */
function CsvAccessEditor(props: {
  catalog: CsvCatalogEntry[];
  value: CsvAccess;
  onChange: (next: CsvAccess) => void;
}) {
  const importable = props.catalog.filter((c) => c.importable);
  return (
    <Field
      label="CSV import & export"
      hint="Which data tabs this role may export, import, and approve imports for.
        These apply on top of the module's Read level; approving a tab also lets
        you import it, and an importer who cannot approve has their file queued
        for someone who can."
    >
      <Row gap={2} className={styles.grantRow}>
        <GrantSelect
          label="Export"
          options={props.catalog}
          selected={props.value.export}
          onChange={(keys) => props.onChange({ ...props.value, export: keys })}
        />
        <GrantSelect
          label="Import"
          options={importable}
          selected={props.value.import}
          onChange={(keys) => props.onChange({ ...props.value, import: keys })}
        />
        <GrantSelect
          label="Approve imports"
          options={importable}
          selected={props.value.approve_import}
          onChange={(keys) =>
            props.onChange({ ...props.value, approve_import: keys })
          }
        />
      </Row>
    </Field>
  );
}

function GrantSelect(props: {
  label: string;
  options: CsvCatalogEntry[];
  selected: string[];
  onChange: (keys: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  // Show only the tabs that exist, so a stale grant for a removed tab is dropped.
  const known = new Set(props.options.map((o) => o.key));
  const count = props.selected.filter((k) => known.has(k)).length;

  function toggle(key: string) {
    props.onChange(
      props.selected.includes(key)
        ? props.selected.filter((k) => k !== key)
        : [...props.selected, key],
    );
  }

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      side="bottom"
      align="start"
      size="lg"
      trigger={
        <Button type="button" variant="secondary" size="compact">
          {props.label}: {count === 0 ? "none" : `${count} selected`}
        </Button>
      }
    >
      <div className={styles.grantList}>
        {props.options.map((o) => (
          <Checkbox
            key={o.key}
            label={o.label}
            checked={props.selected.includes(o.key)}
            onCheckedChange={() => toggle(o.key)}
          />
        ))}
      </div>
    </Popover>
  );
}
