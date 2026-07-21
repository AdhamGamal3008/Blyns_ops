// Employees (§1.2): invite within seat limit, edit role, block/unlock/reset.

import { UserPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  Banner,
  Button,
  CardHeader,
  DataState,
  DataTable,
  type DataTableColumn,
  errorText,
  Field,
  FormModal,
  Input,
  NativeSelect,
  Row,
  Select,
} from "../../shared/ui";
import styles from "./RolesSection.module.css";

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

  const columns: DataTableColumn<Employee>[] = [
    { key: "name", header: "Name", sortable: true, accessor: (e) => <b>{e.name}</b> },
    { key: "email", header: "Email", sortable: true },
    {
      key: "role",
      header: "Role",
      sortable: true,
      sortValue: (e) => roleName(e.role_id),
      accessor: (e) =>
        props.canWrite ? (
          <NativeSelect
            selectSize="compact"
            aria-label={`Role for ${e.name}`}
            value={e.role_id}
            onChange={(ev) =>
              act(`/settings/employees/${e.id}`, { role_id: ev.target.value }, "PATCH")}
            options={roles.map((r) => ({ value: r.id, label: r.name }))}
          />
        ) : (
          roleName(e.role_id)
        ),
    },
    {
      key: "status",
      header: "Status",
      accessor: (e) => (
        <Row gap={2} className={styles.noWrap}>
          {e.is_blocked ? (
            <Badge tone="danger">blocked</Badge>
          ) : e.locked_until && new Date(e.locked_until) > new Date() ? (
            <Badge tone="warning">locked</Badge>
          ) : (
            <Badge tone="success">active</Badge>
          )}
          {e.must_reset_password && <Badge tone="neutral">reset pending</Badge>}
        </Row>
      ),
    },
    ...(props.canWrite
      ? [{
          key: "actions",
          header: "",
          accessor: (e: Employee) => (
            <Row gap={2} className={styles.noWrap}>
              <Button variant="ghost" size="compact" title="Issue a new temp password"
                onClick={() => act(`/settings/employees/${e.id}/reset-password`)}>
                Reset PW
              </Button>
              <Button variant="ghost" size="compact" title="Clear failed-login lockout"
                onClick={() => act(`/settings/employees/${e.id}/unlock`)}>
                Unlock
              </Button>
              {e.is_blocked ? (
                <Button variant="ghost" size="compact" onClick={() =>
                  act(`/settings/employees/${e.id}/block`, { blocked: false }, "PATCH")}>
                  Unblock
                </Button>
              ) : (
                <Button variant="danger" size="compact" onClick={() =>
                  act(`/settings/employees/${e.id}/block`, { blocked: true }, "PATCH")}>
                  Block
                </Button>
              )}
            </Row>
          ),
        }]
      : []),
  ];

  return (
    <section>
      <CardHeader
        title="Employees"
        description={employees ? `${employees.length} using a seat` : "Who can sign in"}
        actions={
          props.canWrite && (
            <Button size="compact" onClick={() => setShowInvite(true)}>
              <UserPlus size={15} aria-hidden="true" />
              Invite employee
            </Button>
          )
        }
      />

      {error != null && employees != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      {tempPw && (
        <Banner
          tone="warning"
          title={`One-time temp password for ${tempPw.email}`}
          onDismiss={() => setTempPw(null)}
        >
          <code className={styles.tempPw}>{tempPw.pw}</code>
          <span> — shown once; a reset is forced on first login.</span>
        </Banner>
      )}

      <DataState
        loading={!employees && !error}
        error={employees ? null : error}
        onRetry={load}
        isEmpty={employees?.length === 0}
        emptyTitle="No employees yet"
      >
        <DataTable
          data={employees ?? []}
          columns={columns}
          getRowId={(e) => e.id}
          searchPlaceholder="Search employees…"
        />
      </DataState>

      <InviteModal
        open={showInvite}
        roles={roles}
        onDone={(pw, email) => {
          setShowInvite(false);
          if (pw) {
            setError(null);
            setTempPw({ email, pw });
          }
          load();
        }}
      />
    </section>
  );
}

function InviteModal(props: {
  open: boolean;
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
    <FormModal
      open={props.open}
      onOpenChange={(o) => !o && props.onDone(null, "")}
      title="Invite employee"
      description="Creates the account and issues a one-time password. This uses a seat."
      onSubmit={submit}
      error={error}
      errorTitle="Could not create the employee"
      busy={busy}
      submitLabel="Create (uses a seat)"
      busyLabel="Creating…"
    >
      <Field label="Name" required>
        <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus required />
      </Field>
      <Field label="Email" required>
        <Input type="email" value={email} required
          onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Role">
        <Select
          value={roleId || props.roles[0]?.id}
          onValueChange={setRoleId}
          options={props.roles.map((r) => ({ value: r.id, label: r.name }))}
        />
      </Field>
    </FormModal>
  );
}
