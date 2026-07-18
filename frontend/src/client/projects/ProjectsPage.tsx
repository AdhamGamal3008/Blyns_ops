// Project Management portfolio (docs/modules/PROJECT_MANAGEMENT.md §12). The
// list is the entry point; a row opens the 16-stage detail view.

import { useCallback, useEffect, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { api } from "../../shared/api";
import type { ClientMe } from "../../shared/types";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/ui";
import { PROJECT_TONE, humanize, money, type Project } from "./types";

export function ProjectsPage() {
  const me = useOutletContext<ClientMe>();
  const navigate = useNavigate();
  const canWrite = (me.role.permissions["projects"] ?? 0) >= 3;
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api<Project[]>("/projects?page_size=100")
      .then((r) => setProjects(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  if (!projects) return <Spinner />;

  return (
    <>
      <Card
        title={`Projects (${projects.length})`}
        actions={canWrite && (
          <Button onClick={() => setCreating(true)}>New project</Button>
        )}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>Code</th><th>Name</th><th>Stage</th><th>Status</th>
              <th style={{ textAlign: "right" }}>Planned budget</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.id} style={{ cursor: "pointer" }}
                onClick={() => navigate(`/app/projects/${p.id}`)}>
                <td className="muted">{p.code ?? "—"}</td>
                <td><b>{p.name}</b></td>
                <td className="muted">
                  {p.current_stage_order ? `${p.current_stage_order}/16 · ` : ""}
                  {humanize(p.current_stage_key)}
                </td>
                <td>
                  <Badge tone={PROJECT_TONE[p.status] ?? "neutral"}>
                    {(p.status ?? "—").replace("_", " ")}
                  </Badge>
                </td>
                <td style={{ textAlign: "right" }}>
                  {money(p.budget?.planned ?? 0, p.budget?.currency ?? "USD")}
                </td>
              </tr>
            ))}
            {projects.length === 0 && (
              <tr><td colSpan={5} className="muted">
                No projects yet.{canWrite && " Create one to start the stage machine."}
              </td></tr>
            )}
          </tbody>
        </table>
      </Card>
      {creating && (
        <ProjectModal onDone={(id) => {
          setCreating(false);
          if (id) navigate(`/app/projects/${id}`);
        }} />
      )}
    </>
  );
}

interface AccountOption { id: string; name: string }

function ProjectModal(props: { onDone: (createdId: string | null) => void }) {
  const [name, setName] = useState("");
  const [scope, setScope] = useState("");
  const [budget, setBudget] = useState("0");
  const [accountId, setAccountId] = useState("");
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // linking a CRM account is optional (§1); offer it only if CRM is readable
    api<AccountOption[]>("/crm/accounts?page_size=100")
      .then((r) => setAccounts(r.data)).catch(() => setAccounts([]));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await api<Project>("/projects", {
        method: "POST",
        body: {
          name,
          scope: scope || null,
          crm_account_id: accountId || null,
          planned_budget: Number(budget),
        },
      });
      props.onDone(r.data.id);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => props.onDone(null)}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 4 }}>New project</h3>
        <p className="muted" style={{ marginBottom: 16, fontSize: 13 }}>
          Enters the machine at Stage 1 (Lead Conversion), waiting on its
          onboarding documents.
        </p>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Name">
            <input value={name} onChange={(e) => setName(e.target.value)} required
              placeholder="e.g. Tower A Lobby Cladding" />
          </Field>
          <Field label="Scope">
            <input value={scope} onChange={(e) => setScope(e.target.value)}
              placeholder="Short description of the works" />
          </Field>
          <Field label="Client account (CRM)">
            <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
              <option value="">— none —</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Planned budget">
            <input type="number" step="any" min="0" value={budget}
              onChange={(e) => setBudget(e.target.value)} />
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(null)}>Cancel</Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create project"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
