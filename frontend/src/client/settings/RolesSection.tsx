// Client roles RBAC editor (§1.3): every resource gets a 4-way selector
// (None / View / Read / Write) — the role editor contract.

import { Plus, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  Banner,
  Button,
  CardHeader,
  DataState,
  errorText,
  Field,
  FormModal,
  Input,
  Row,
  Stack,
} from "../../shared/ui";
import { CLIENT_RESOURCES, LevelChip, RoleMatrix } from "./RoleMatrix";
import styles from "./RolesSection.module.css";

interface Role {
  id: string;
  name: string;
  permissions: Record<string, number>;
  is_system?: boolean;
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
                  <th key={r} scope="col" className={styles.resHead}>{r}</th>
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
                    <td key={r} className={styles.levelCell} data-label={r}>
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
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (props.role) {
        await api(`/settings/roles/${props.role.id}`, {
          method: "PATCH", body: { name, permissions: perms },
        });
      } else {
        await api("/settings/roles", {
          method: "POST", body: { name, permissions: perms },
        });
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
      </Stack>
    </FormModal>
  );
}
