// Employees (§1.2): invite within seat limit, edit role, block/unlock/reset.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/legacy-ui";

interface Employee {
  id: string;
  name: string;
  email: string;
  role_id: string;
  is_blocked?: boolean;
  locked_until?: string | null;
  must_reset_password?: boolean;
}

interface Role {
  id: string;
  name: string;
}

export function EmployeesSection(props: { canWrite: boolean }) {
  const [employees, setEmployees] = useState<Employee[] | null>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [showInvite, setShowInvite] = useState(false);
  const [tempPw, setTempPw] = useState<{ email: string; pw: string } | null>(null);

  const load = useCallback(() => {
    api<Employee[]>("/settings/employees").then((r) => setEmployees(r.data)).catch(setError);
    api<Role[]>("/settings/roles").then((r) => setRoles(r.data)).catch(() => {});
  }, []);

  useEffect(load, [load]);

  const roleName = (id: string) => roles.find((r) => r.id === id)?.name ?? "—";

  async function act(path: string, body?: unknown, method = "POST") {
    setError(null);
    try {
      const res = await api<{ temp_password?: string }>(path, { method, body });
      if (res.data?.temp_password) {
        const uid = path.split("/")[3];
        const emp = employees?.find((e) => e.id === uid);
        setTempPw({ email: emp?.email ?? "", pw: res.data.temp_password });
      }
      load();
    } catch (err) {
      setError(err);
    }
  }

  if (!employees) return <Spinner />;

  return (
    <>
      <Card
        title={`Employees (${employees.length})`}
        actions={props.canWrite && (
          <Button onClick={() => setShowInvite(true)}>Invite employee</Button>
        )}
      >
        <ErrorNote error={error} />
        {tempPw && (
          <div style={{ marginBottom: 12 }}>
            <p className="muted">
              One-time temp password for <b>{tempPw.email}</b> (reset forced on
              first login):
            </p>
            <div className="temp-pw">{tempPw.pw}</div>
          </div>
        )}
        <table className="table">
          <thead>
            <tr>
              <th>Name</th><th>Email</th><th>Role</th><th>Status</th>
              {props.canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {employees.map((e) => (
              <tr key={e.id}>
                <td><b>{e.name}</b></td>
                <td className="muted">{e.email}</td>
                <td>
                  {props.canWrite ? (
                    <select value={e.role_id} style={{ width: 140 }}
                      onChange={(ev) =>
                        act(`/settings/employees/${e.id}`,
                            { role_id: ev.target.value }, "PATCH")}>
                      {roles.map((r) => (
                        <option key={r.id} value={r.id}>{r.name}</option>
                      ))}
                    </select>
                  ) : roleName(e.role_id)}
                </td>
                <td>
                  {e.is_blocked ? <Badge tone="danger">blocked</Badge>
                    : e.locked_until && new Date(e.locked_until) > new Date()
                      ? <Badge tone="warn">locked</Badge>
                      : <Badge tone="ok">active</Badge>}
                  {e.must_reset_password && <> <Badge>reset pending</Badge></>}
                </td>
                {props.canWrite && (
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <Button variant="ghost" title="Reset password"
                      onClick={() => act(`/settings/employees/${e.id}/reset-password`)}>
                      Reset PW
                    </Button>{" "}
                    <Button variant="ghost" title="Clear failed-login lockout"
                      onClick={() => act(`/settings/employees/${e.id}/unlock`)}>
                      Unlock
                    </Button>{" "}
                    {e.is_blocked ? (
                      <Button variant="ghost" onClick={() =>
                        act(`/settings/employees/${e.id}/block`,
                            { blocked: false }, "PATCH")}>
                        Unblock
                      </Button>
                    ) : (
                      <Button variant="danger" onClick={() =>
                        act(`/settings/employees/${e.id}/block`,
                            { blocked: true }, "PATCH")}>
                        Block
                      </Button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {showInvite && (
        <InviteModal roles={roles}
          onDone={(pw, email) => {
            setShowInvite(false);
            if (pw) {
              setError(null);
              setTempPw({ email, pw });
            }
            load();
          }} />
      )}
    </>
  );
}

function InviteModal(props: {
  roles: Role[];
  onDone: (tempPw: string | null, email: string) => void;
}) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [roleId, setRoleId] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await api<{ temp_password: string }>("/settings/employees", {
        method: "POST",
        body: { name, email, role_id: roleId || props.roles[0]?.id },
      });
      props.onDone(res.data.temp_password, email);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => props.onDone(null, "")}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 16 }}>Invite employee</h3>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Name">
            <input value={name} onChange={(e) => setName(e.target.value)}
              autoFocus required />
          </Field>
          <Field label="Email">
            <input type="email" value={email} required
              onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Role">
            <select value={roleId || props.roles[0]?.id}
              onChange={(e) => setRoleId(e.target.value)}>
              {props.roles.map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <Button variant="ghost" onClick={() => props.onDone(null, "")}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create (uses a seat)"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
