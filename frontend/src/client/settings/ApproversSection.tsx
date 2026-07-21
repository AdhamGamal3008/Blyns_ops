// Approver-role map (PROJECT_MANAGEMENT.md §9): resolve each position to one
// or more client roles. Consumed by the stage-gate approval engine (Phase 10).

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  Banner,
  CardHeader,
  Checkbox,
  DataState,
  errorText,
  Row,
} from "../../shared/ui";
import styles from "./RolesSection.module.css";

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

  const holds = (entry: MapEntry, roleName: string) =>
    entry.client_roles.some((cr) => cr.toLowerCase() === roleName.toLowerCase());

  async function toggle(entry: MapEntry, roleName: string) {
    const next = holds(entry, roleName)
      ? entry.client_roles.filter((r) => r.toLowerCase() !== roleName.toLowerCase())
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

  return (
    <section>
      <CardHeader
        title="Approver roles"
        description="Which client roles can sign off each stage-gate position."
      />

      {error != null && entries != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!entries && !error}
        error={entries ? null : error}
        onRetry={load}
        isEmpty={entries?.length === 0}
        emptyTitle="No approver positions"
      >
        <div className={styles.scroll}>
          <table className={styles.overview}>
            <thead>
              <tr>
                <th scope="col" className={styles.roleHead}>Position</th>
                <th scope="col" className={styles.roleHead}>Resolves to client roles</th>
              </tr>
            </thead>
            <tbody>
              {(entries ?? []).map((e) => (
                <tr key={e.id}>
                  <th scope="row" className={styles.roleCell}>
                    <span className={styles.roleName}>{e.approver_role}</span>
                  </th>
                  <td className={styles.roleCell}>
                    <Row gap={4}>
                      {roles.map((r) =>
                        props.canWrite ? (
                          <Checkbox
                            key={r.id}
                            label={r.name}
                            checked={holds(e, r.name)}
                            onCheckedChange={() => toggle(e, r.name)}
                          />
                        ) : (
                          holds(e, r.name) && (
                            <Badge key={r.id} tone="brand">{r.name}</Badge>
                          )
                        ),
                      )}
                    </Row>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </DataState>
    </section>
  );
}
