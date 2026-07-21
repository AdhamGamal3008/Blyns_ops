// Approver-role map (PROJECT_MANAGEMENT.md §9): resolve each position to one
// or more client roles. Consumed by the stage-gate approval engine (Phase 10).

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Button, Card, ErrorNote, Spinner } from "../../shared/legacy-ui";

interface MapEntry {
  id: string;
  approver_role: string;
  client_roles: string[];
  assigned_user_ids: string[];
}

interface Role {
  id: string;
  name: string;
}

export function ApproversSection(props: { canWrite: boolean }) {
  const [entries, setEntries] = useState<MapEntry[] | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<MapEntry[]>("/settings/approver-roles")
      .then((r) => setEntries(r.data)).catch(setError);
    api<Role[]>("/settings/roles").then((r) => setRoles(r.data)).catch(() => {});
  }, []);

  useEffect(load, [load]);

  async function toggle(entry: MapEntry, roleName: string) {
    const next = entry.client_roles.includes(roleName)
      ? entry.client_roles.filter((r) => r !== roleName)
      : [...entry.client_roles, roleName];
    setError(null);
    try {
      await api(`/settings/approver-roles/${entry.approver_role}`, {
        method: "PATCH", body: { client_roles: next },
      });
      load();
    } catch (err) {
      setError(err);
    }
  }

  if (!entries) return <Spinner />;

  return (
    <Card title="Approver roles → client roles (stage-gate approvals)">
      <ErrorNote error={error} />
      <table className="table">
        <thead>
          <tr><th>Position</th><th>Resolves to client roles</th></tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.id}>
              <td><b>{e.approver_role}</b></td>
              <td>
                <div className="quick-actions">
                  {roles.map((r) => (
                    props.canWrite ? (
                      <label key={r.id}
                        style={{ display: "flex", gap: 4, fontSize: 12 }}>
                        <input type="checkbox" style={{ width: "auto" }}
                          checked={e.client_roles.some(
                            (cr) => cr.toLowerCase() === r.name.toLowerCase(),
                          )}
                          onChange={() => toggle(e, r.name)} />
                        {r.name}
                      </label>
                    ) : (
                      e.client_roles.some(
                        (cr) => cr.toLowerCase() === r.name.toLowerCase(),
                      ) && <Button key={r.id} variant="ghost">{r.name}</Button>
                    )
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
