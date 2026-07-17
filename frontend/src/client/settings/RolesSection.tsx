// Client roles RBAC editor (§1.3): every resource gets a 4-way selector
// (None / View / Read / Write) — the role editor contract.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/ui";

const CLIENT_RESOURCES = [
  "dashboard", "calendar", "activity",
  "projects", "crm", "inventory", "finance", "settings",
];
const LEVELS = ["None", "View", "Read", "Write"];

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

  if (!roles) return <Spinner />;

  return (
    <>
      <Card
        title="Client roles"
        actions={props.canWrite && (
          <Button onClick={() => setEditing("new")}>New role</Button>
        )}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>Role</th>
              {CLIENT_RESOURCES.map((r) => <th key={r}>{r}</th>)}
              {props.canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {roles.map((role) => (
              <tr key={role.id}>
                <td>
                  <b>{role.name}</b>{" "}
                  {role.is_system && <Badge>seeded</Badge>}
                </td>
                {CLIENT_RESOURCES.map((r) => (
                  <td key={r} className="muted">
                    {LEVELS[role.permissions[r] ?? 0]}
                  </td>
                ))}
                {props.canWrite && (
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <Button variant="ghost" onClick={() => setEditing(role)}>
                      Edit
                    </Button>{" "}
                    <Button variant="ghost" onClick={() => remove(role)}>
                      Delete
                    </Button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {editing && (
        <RoleEditor
          role={editing === "new" ? null : editing}
          onDone={() => { setEditing(null); load(); }}
        />
      )}
    </>
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

  return (
    <div className="modal-backdrop" onClick={props.onDone}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 16 }}>
          {props.role ? `Edit role: ${props.role.name}` : "New role"}
        </h3>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Role name">
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <table className="table">
            <thead>
              <tr><th>Resource</th>{LEVELS.map((l) => <th key={l}>{l}</th>)}</tr>
            </thead>
            <tbody>
              {CLIENT_RESOURCES.map((res) => (
                <tr key={res}>
                  <td><b>{res}</b></td>
                  {LEVELS.map((_, level) => (
                    <td key={level}>
                      <input type="radio" style={{ width: "auto" }}
                        name={`perm-${res}`}
                        checked={perms[res] === level}
                        onChange={() => setPerms({ ...perms, [res]: level })} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={props.onDone}>Cancel</Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Save role"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
