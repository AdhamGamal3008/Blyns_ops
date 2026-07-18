// One stage's control surface (§4/§5/§6/§8): entry documents, physical gates,
// automated tasks, and the submit → approve / reject flow. Every mutation
// refreshes both this panel and the parent timeline/budget.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/ui";
import {
  STAGE_TONE, humanize,
  type GateRule, type StageDetail, type ValidationCheck,
} from "./types";

export function StagePanel(props: {
  projectId: string;
  order: number;
  canWrite: boolean;
  canApprove: boolean;
  onChanged: () => void;
}) {
  const { projectId, order, canWrite, canApprove } = props;
  const [detail, setDetail] = useState<StageDetail | null>(null);
  const [gateRules, setGateRules] = useState<Record<string, GateRule>>({});
  const [error, setError] = useState<unknown>(null);
  const [notReached, setNotReached] = useState(false);
  const [busy, setBusy] = useState(false);
  const [validation, setValidation] = useState<ValidationCheck[] | null>(null);
  const [logging, setLogging] = useState<GateRule | null>(null);
  const [rejecting, setRejecting] = useState(false);

  const load = useCallback(() => {
    setError(null);
    setNotReached(false);
    api<StageDetail>(`/projects/${projectId}/stages/${order}`)
      .then((r) => setDetail(r.data))
      .catch((e) => {
        if (e?.status === 404) setNotReached(true);
        else setError(e);
      });
  }, [projectId, order]);

  useEffect(load, [load]);
  useEffect(() => {
    api<GateRule[]>(`/projects/config/gates`)
      .then((r) => setGateRules(Object.fromEntries(r.data.map((g) => [g.key, g]))))
      .catch(() => setGateRules({}));
  }, []);

  const refresh = () => { load(); props.onChanged(); };

  async function act(run: () => Promise<unknown>, keepValidation = false) {
    setBusy(true);
    setError(null);
    if (!keepValidation) setValidation(null);
    try {
      await run();
      refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ validation: { passed: boolean; checks: ValidationCheck[] } }>(
        `/projects/${projectId}/stages/${order}/submit`, { method: "POST", body: {} });
      setValidation(r.data.validation.checks);
      refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  if (notReached) {
    return (
      <Card title={`Stage ${order}`}>
        <p className="muted">This stage has not been reached yet.</p>
      </Card>
    );
  }
  if (!detail) return <Card><Spinner /></Card>;

  const { definition, instance, evaluation, approval } = detail;
  const supplied = new Set(instance.documents_supplied ?? []);
  const docGates = definition.entry_gates.filter((g) => g.type === "document");
  const status = instance.status;

  return (
    <Card
      title={`Stage ${definition.order} · ${definition.name}`}
      actions={<Badge tone={STAGE_TONE[status]}>{status.replace("_", " ")}</Badge>}
    >
      <ErrorNote error={error} />

      {instance.blocking_reason && (
        <p className="step-block" style={{ marginTop: 0 }}>{instance.blocking_reason}</p>
      )}
      <p className="muted" style={{ fontSize: 13 }}>
        Approver: <b>{humanize(definition.approver_role ?? "—")}</b>
        {definition.co_approver_roles?.length
          ? ` · co-approver ${definition.co_approver_roles.map(humanize).join(", ")}` : ""}
        {instance.recovery_loops > 0 && ` · ↻ ${instance.recovery_loops} recovery loop(s)`}
      </p>

      {/* entry documents (§6 document check) */}
      {docGates.length > 0 && (
        <Section title="Entry documents">
          {docGates.map((g) => (
            <Row key={g.key} label={humanize(g.key)}>
              {supplied.has(g.key)
                ? <Badge tone="ok">supplied</Badge>
                : canWrite
                  ? <Button variant="ghost" disabled={busy}
                      onClick={() => act(() => api(
                        `/projects/${projectId}/stages/${order}/documents/${g.key}`,
                        { method: "POST", body: {} }))}>Mark supplied</Button>
                  : <Badge tone="warn">missing</Badge>}
            </Row>
          ))}
        </Section>
      )}

      {/* physical gates (§8) */}
      {definition.quality_gates.length > 0 && (
        <Section title="Quality gates">
          {definition.quality_gates.map((key) => {
            const result = detail.gate_results
              .filter((r) => r.gate_key === key).at(-1);
            return (
              <Row key={key} label={humanize(key)}>
                {result
                  ? <Badge tone={result.severe ? "danger" : result.passed ? "ok" : "warn"}>
                      {result.severe ? "severe" : result.passed ? "passed" : "failed"}
                    </Badge>
                  : <Badge tone="neutral">no result</Badge>}
                {canWrite && gateRules[key] && (
                  <Button variant="ghost" disabled={busy}
                    onClick={() => setLogging(gateRules[key])}>Log result</Button>
                )}
              </Row>
            );
          })}
        </Section>
      )}

      {/* automated tasks (§6) */}
      {(instance.task_results?.length ?? 0) > 0 && (
        <Section title="Automated tasks">
          {instance.task_results!.map((t) => (
            <Row key={t.task} label={humanize(t.task)}>
              <Badge tone={t.status === "done" ? "ok" : "neutral"}>{t.status}</Badge>
              {canWrite && (
                <Button variant="ghost" disabled={busy}
                  onClick={() => act(() => api(
                    `/projects/${projectId}/stages/${order}/tasks/${t.task}/run`,
                    { method: "POST" }))}>Re-run</Button>
              )}
            </Row>
          ))}
        </Section>
      )}

      {/* blockers surfaced by the decision engine */}
      {(evaluation.waiting_on.length > 0 || evaluation.blocked_by.length > 0) && (
        <Section title="Blockers">
          {[...evaluation.waiting_on, ...evaluation.blocked_by].map((b) => (
            <p key={b} className="muted" style={{ fontSize: 13, margin: "2px 0" }}>• {b}</p>
          ))}
        </Section>
      )}

      {/* auto-validation result (from submit, or a pending approval) */}
      {(validation ?? approval?.auto_validation?.checks) && (
        <Section title="Automated validation">
          {(validation ?? approval!.auto_validation!.checks).map((c) => (
            <Row key={c.key} label={humanize(c.key)}>
              <Badge tone={c.passed ? "ok" : "danger"}>{c.passed ? "pass" : "fail"}</Badge>
              <span className="muted" style={{ fontSize: 12 }}>{c.detail}</span>
            </Row>
          ))}
        </Section>
      )}

      {/* actions */}
      <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
        {canWrite && ["in_progress", "waiting", "blocked", "validation", "rejected"].includes(status) && (
          <Button disabled={busy} onClick={submit}>Submit for approval</Button>
        )}
        {status === "pending_approval" && canApprove && (
          <>
            <Button disabled={busy}
              onClick={() => act(() => api(
                `/projects/${projectId}/stages/${order}/approve`,
                { method: "POST", body: {} }))}>Approve</Button>
            <Button variant="danger" disabled={busy}
              onClick={() => setRejecting(true)}>Reject</Button>
          </>
        )}
        {status === "approved" && <span className="muted">Stage approved.</span>}
        {status === "on_hold" && (
          <span className="muted">On hold — resolve the open report to continue.</span>
        )}
      </div>

      {logging && (
        <GateResultModal projectId={projectId} order={order} rule={logging}
          onDone={(ok) => { setLogging(null); if (ok) refresh(); }} />
      )}
      {rejecting && (
        <RejectModal projectId={projectId} order={order}
          onDone={(ok) => { setRejecting(false); if (ok) refresh(); }} />
      )}
    </Card>
  );
}

function Section(props: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 14 }}>
      <div className="kpi-label" style={{ fontSize: 11, marginBottom: 4 }}>{props.title}</div>
      {props.children}
    </div>
  );
}

function Row(props: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0" }}>
      <span style={{ flex: 1, fontSize: 13 }}>{props.label}</span>
      {props.children}
    </div>
  );
}

function GateResultModal(props: {
  projectId: string; order: number; rule: GateRule;
  onDone: (ok: boolean) => void;
}) {
  const { rule } = props;
  const isInspection = rule.type === "inspection";
  const checklist = rule.checklist ?? [];
  const [readings, setReadings] = useState<{ location: string; value: string }[]>(
    [{ location: "", value: "" }]);
  const [checks, setChecks] = useState<Record<string, boolean>>(
    Object.fromEntries(checklist.map((c) => [c, true])));
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/projects/${props.projectId}/stages/${props.order}/gates/${rule.key}/result`, {
        method: "POST",
        body: isInspection
          ? { checklist_results: checklist.map((c) => ({ item: c, passed: checks[c] })), notes }
          : {
              readings: readings
                .filter((r) => r.value !== "")
                .map((r) => ({ location: r.location || "reading", value: Number(r.value) })),
              notes,
            },
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
        <h3 style={{ marginBottom: 4 }}>Log {humanize(rule.key)}</h3>
        <p className="muted" style={{ marginBottom: 14, fontSize: 13 }}>
          The engine scores this against the seeded threshold — you record the
          readings, not the verdict.
        </p>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          {isInspection ? (
            checklist.map((c) => (
              <label key={c} style={{ display: "flex", gap: 8, alignItems: "center", padding: "4px 0" }}>
                <input type="checkbox" style={{ width: "auto" }} checked={checks[c]}
                  onChange={(e) => setChecks({ ...checks, [c]: e.target.checked })} />
                <span style={{ fontSize: 13 }}>{c}</span>
              </label>
            ))
          ) : (
            <>
              {readings.map((r, i) => (
                <div key={i} style={{ display: "flex", gap: 8 }}>
                  <Field label="Location">
                    <input value={r.location} placeholder="e.g. panel-A"
                      onChange={(e) => {
                        const next = [...readings];
                        next[i] = { ...r, location: e.target.value };
                        setReadings(next);
                      }} />
                  </Field>
                  <Field label="Value">
                    <input type="number" step="any" value={r.value} required
                      onChange={(e) => {
                        const next = [...readings];
                        next[i] = { ...r, value: e.target.value };
                        setReadings(next);
                      }} />
                  </Field>
                </div>
              ))}
              <Button variant="ghost"
                onClick={() => setReadings([...readings, { location: "", value: "" }])}>
                + Add reading
              </Button>
            </>
          )}
          <Field label="Notes">
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Log result"}</Button>
          </div>
        </form>
      </div>
    </div>
  );
}

const REPORT_TYPES = [
  "change", "issue", "ncr", "capa", "rfi", "missing_information", "qa",
] as const;

function RejectModal(props: {
  projectId: string; order: number; onDone: (ok: boolean) => void;
}) {
  const [comment, setComment] = useState("");
  const [type, setType] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/projects/${props.projectId}/stages/${props.order}/reject`, {
        method: "POST",
        body: { comment, report_type: type || null },
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
        <h3 style={{ marginBottom: 4 }}>Reject stage</h3>
        <p className="muted" style={{ marginBottom: 14, fontSize: 13 }}>
          Opens a typed report, increments the recovery loop, and reopens the
          stage for resubmission.
        </p>
        <ErrorNote error={error} />
        <form onSubmit={submit}>
          <Field label="Reason (required)">
            <input value={comment} onChange={(e) => setComment(e.target.value)} required
              placeholder="What must change before resubmission" />
          </Field>
          <Field label="Report type (optional — defaults to the stage's recovery type)">
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">— default —</option>
              {REPORT_TYPES.map((t) => (
                <option key={t} value={t}>{humanize(t)}</option>
              ))}
            </select>
          </Field>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
            <Button variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
            <Button type="submit" variant="danger" disabled={busy}>
              {busy ? "Rejecting…" : "Reject stage"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
