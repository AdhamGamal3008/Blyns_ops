// Typed exception reports (§3.8): Missing Info / Issue / Change / NCR / CAPA /
// RFI / QA. Resolving the last open report on a held project clears the hold
// (§4), so a resolve refreshes the parent too.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/ui";
import { REPORT_TONE, humanize, type Report, type ReportType } from "./types";

const TYPES: ReportType[] = [
  "issue", "change", "ncr", "capa", "rfi", "missing_information", "qa",
];

export function ReportsSection(props: {
  projectId: string; canWrite: boolean; onChanged: () => void;
}) {
  const [items, setItems] = useState<Report[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api<Report[]>(`/projects/${props.projectId}/reports?page_size=100`)
      .then((r) => setItems(r.data)).catch(setError);
  }, [props.projectId]);

  useEffect(load, [load]);

  async function setStatus(r: Report, status: string) {
    setError(null);
    try {
      await api(`/projects/${props.projectId}/reports/${r.id}`, {
        method: "PATCH", body: { status },
      });
      load();
      props.onChanged(); // resolving may clear an on_hold project
    } catch (e) {
      setError(e);
    }
  }

  if (!items) return <Spinner />;

  const open = items.filter((r) => r.status === "open" || r.status === "in_progress").length;

  return (
    <>
      <Card
        title={`Reports (${open} open / ${items.length})`}
        actions={props.canWrite && (
          <Button onClick={() => setCreating(true)}>New report</Button>
        )}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>Title</th><th>Type</th><th>Status</th>
              {props.canWrite && <th></th>}
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.id}>
                <td><b>{r.title}</b></td>
                <td><Badge tone="neutral">{humanize(r.type)}</Badge></td>
                <td><Badge tone={REPORT_TONE[r.status]}>{r.status.replace("_", " ")}</Badge></td>
                {props.canWrite && (
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    {(r.status === "open" || r.status === "in_progress") && (
                      <>
                        {r.status === "open" && (
                          <Button variant="ghost" onClick={() => setStatus(r, "in_progress")}>
                            Start
                          </Button>
                        )}{" "}
                        <Button variant="ghost" onClick={() => setStatus(r, "resolved")}>
                          Resolve
                        </Button>
                      </>
                    )}
                  </td>
                )}
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={props.canWrite ? 4 : 3} className="muted">
                No reports — nothing has gone wrong yet.
              </td></tr>
            )}
          </tbody>
        </table>
      </Card>
      {creating && (
        <ReportModal projectId={props.projectId}
          onDone={(ok) => { setCreating(false); if (ok) load(); }} />
      )}
    </>
  );
}

function ReportModal(props: { projectId: string; onDone: (ok: boolean) => void }) {
  const [type, setType] = useState<ReportType>("issue");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/projects/${props.projectId}/reports`, {
        method: "POST", body: { type, title, details: {} },
      });
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={() => props.onDone(false)}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 14 }}>New report</h3>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Type">
            <select value={type} onChange={(e) => setType(e.target.value as ReportType)}>
              {TYPES.map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
            </select>
          </Field>
          <Field label="Title">
            <input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Create"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}
