// One stage's control surface (§4/§5/§6/§8): entry documents, physical gates,
// automated tasks, and the submit → approve / reject flow. Every mutation
// refreshes both this panel and the parent timeline/budget.

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  Banner,
  Button,
  Card,
  CardHeader,
  Checkbox,
  DataState,
  EmptyState,
  errorText,
  Field,
  Input,
  Modal,
  Row,
  Select,
  Stack,
} from "../../shared/ui";
import {
  STAGE_TONE, humanize,
  type Deliverable, type EntryGate, type GateRule, type StageDetail, type ValidationCheck,
} from "./types";
import styles from "./StagePanel.module.css";

const NO_REF = "__noref"; // "attach no document" option in the reference picker

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
  const [docs, setDocs] = useState<Deliverable[]>([]);
  const [refFor, setRefFor] = useState<Record<string, string>>({});

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
  // project documents, for optionally referencing one as a gate's evidence
  useEffect(() => {
    api<Deliverable[]>(`/projects/${projectId}/deliverables?page_size=100`)
      .then((r) => setDocs(Array.isArray(r.data) ? r.data : []))
      .catch(() => setDocs([]));
  }, [projectId]);

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
      <Card>
        <EmptyState
          title={`Stage ${order} has not been reached`}
          description="The pipeline opens this stage once the preceding gate is approved."
        />
      </Card>
    );
  }
  if (!detail) {
    return (
      <Card>
        <DataState loading={!error} error={error} onRetry={load}>
          {null}
        </DataState>
      </Card>
    );
  }

  const { definition, instance, evaluation, approval } = detail;
  const supplied = new Set(instance.documents_supplied ?? []);
  const status = instance.status;
  const checks = validation ?? approval?.auto_validation?.checks;

  // Requirements the user clears by "supplying" the gate key (§6 document
  // check). Two kinds share the one supply endpoint: `document` entry gates,
  // and `dependency` gates whose `depends_on` is a foundational PHASE rather
  // than a prior stage (e.g. Stage 14's acclimation_complete →
  // core_material_acclimation). The engine surfaces the latter as `phase:<key>`
  // in waiting_on; a stage→stage dependency instead lands in blocked_by and
  // clears only when that stage is approved, so it must NOT get a manual button.
  const waitingPhases = new Set(
    evaluation.waiting_on
      .filter((w) => w.startsWith("phase:"))
      .map((w) => w.slice("phase:".length)),
  );
  const isPhaseGate = (g: EntryGate) =>
    g.type === "dependency" && !!g.depends_on &&
    (waitingPhases.has(g.depends_on) || supplied.has(g.key));
  const supplyGates = definition.entry_gates.filter(
    (g) => g.type === "document" || isPhaseGate(g),
  );
  // Blockers the user cannot act on here — unapproved prior stages. The
  // suppliable doc/phase gates above own their own controls, so drop them.
  const residualBlockers = [
    ...evaluation.waiting_on.filter(
      (w) => !w.startsWith("doc:") && !w.startsWith("phase:")),
    ...evaluation.blocked_by,
  ];
  // Documents worth attaching to this stage's gates: this stage's own documents
  // plus any general (unassigned) ones. Referencing one is optional.
  const referenceable = docs
    .filter((d) => !d.stage_key || d.stage_key === definition.key)
    .map((d) => ({ value: d.id, label: `${d.title} · ${humanize(d.kind)}` }));
  const refByGate = new Map(
    (instance.document_refs ?? []).map((r) => [r.gate_key, r]),
  );
  const supplyDoc = (gate: EntryGate) => {
    const chosen = refFor[gate.key];
    const body = chosen && chosen !== NO_REF ? { deliverable_id: chosen } : {};
    return act(() => api(
      `/projects/${projectId}/stages/${order}/documents/${gate.key}`,
      { method: "POST", body },
    ));
  };

  return (
    <Card>
      <CardHeader
        title={`Stage ${definition.order} · ${definition.name}`}
        description={
          <>
            Approver <b>{humanize(definition.approver_role ?? "—")}</b>
            {definition.co_approver_roles?.length
              ? ` · co-approver ${definition.co_approver_roles.map(humanize).join(", ")}` : ""}
            {instance.recovery_loops > 0 && ` · ↻ ${instance.recovery_loops} recovery loop(s)`}
          </>
        }
        actions={
          <Badge tone={STAGE_TONE[status] ?? "neutral"}>{status.replace("_", " ")}</Badge>
        }
      />

      <Stack gap={4}>
        {error != null && (
          <Banner tone="danger" title="That action failed">
            {errorText(error)}
          </Banner>
        )}
        {instance.blocking_reason && (
          <Banner tone="warning" title="Blocked">{instance.blocking_reason}</Banner>
        )}

        {/* entry requirements: §6 document check + foundational-phase gates.
            A document gate may optionally reference a project document. */}
        {supplyGates.length > 0 && (
          <Section title="Entry requirements">
            {supplyGates.map((g) => {
              const ref = refByGate.get(g.key);
              const hint = g.type === "dependency"
                ? `phase · ${humanize(g.depends_on)}`
                : ref ? `↳ ${ref.title} (v${ref.version})` : undefined;
              return (
                <ItemRow key={g.key} label={humanize(g.key)} hint={hint}>
                  {supplied.has(g.key) ? (
                    <Badge tone="success">supplied</Badge>
                  ) : canWrite ? (
                    <Row gap={1}>
                      {g.type === "document" && referenceable.length > 0 && (
                        <Select
                          selectSize="compact"
                          value={refFor[g.key] ?? NO_REF}
                          onValueChange={(v) => setRefFor({ ...refFor, [g.key]: v })}
                          options={[
                            { value: NO_REF, label: "— attach a document —" },
                            ...referenceable,
                          ]}
                        />
                      )}
                      <Button variant="ghost" size="compact" disabled={busy}
                        onClick={() => supplyDoc(g)}>Mark supplied</Button>
                    </Row>
                  ) : (
                    <Badge tone="warning">missing</Badge>
                  )}
                </ItemRow>
              );
            })}
          </Section>
        )}

        {/* physical gates (§8) */}
        {definition.quality_gates.length > 0 && (
          <Section title="Quality gates">
            {definition.quality_gates.map((key) => {
              const result = detail.gate_results.filter((r) => r.gate_key === key).at(-1);
              return (
                <ItemRow key={key} label={humanize(key)}>
                  {result
                    ? (
                      <Badge tone={result.severe ? "danger" : result.passed ? "success" : "warning"}>
                        {result.severe ? "severe" : result.passed ? "passed" : "failed"}
                      </Badge>
                    )
                    : <Badge tone="neutral">no result</Badge>}
                  {canWrite && gateRules[key] && (
                    <Button variant="ghost" size="compact" disabled={busy}
                      onClick={() => setLogging(gateRules[key])}>Log result</Button>
                  )}
                </ItemRow>
              );
            })}
          </Section>
        )}

        {/* automated tasks (§6) */}
        {(instance.task_results?.length ?? 0) > 0 && (
          <Section title="Automated tasks">
            {instance.task_results!.map((t) => (
              <ItemRow key={t.task} label={humanize(t.task)}>
                <Badge tone={t.status === "done" ? "success" : "neutral"}>{t.status}</Badge>
                {canWrite && (
                  <Button variant="ghost" size="compact" disabled={busy}
                    onClick={() => act(() => api(
                      `/projects/${projectId}/stages/${order}/tasks/${t.task}/run`,
                      { method: "POST" }))}>Re-run</Button>
                )}
              </ItemRow>
            ))}
          </Section>
        )}

        {/* blockers the user can't clear here — unapproved prior stages */}
        {residualBlockers.length > 0 && (
          <Section title="Blockers">
            <ul className={styles.blockers}>
              {residualBlockers.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </Section>
        )}

        {/* auto-validation result (from submit, or a pending approval) */}
        {checks && (
          <Section title="Automated validation">
            {checks.map((c) => (
              <ItemRow key={c.key} label={humanize(c.key)} hint={c.detail}>
                <Badge tone={c.passed ? "success" : "danger"}>{c.passed ? "pass" : "fail"}</Badge>
              </ItemRow>
            ))}
          </Section>
        )}

        <Row>
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
          {status === "approved" && <span className={styles.note}>Stage approved.</span>}
          {status === "on_hold" && (
            <span className={styles.note}>On hold — resolve the open report to continue.</span>
          )}
        </Row>
      </Stack>

      {logging && (
        <GateResultModal projectId={projectId} order={order} rule={logging}
          onDone={(ok) => { setLogging(null); if (ok) refresh(); }} />
      )}
      <RejectModal open={rejecting} projectId={projectId} order={order}
        onDone={(ok) => { setRejecting(false); if (ok) refresh(); }} />
    </Card>
  );
}

function Section(props: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h4 className={styles.sectionTitle}>{props.title}</h4>
      {props.children}
    </section>
  );
}

function ItemRow(props: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className={styles.itemRow}>
      <span className={styles.itemLabel}>
        {props.label}
        {props.hint && <span className={styles.itemHint}>{props.hint}</span>}
      </span>
      <span className={styles.itemActions}>{props.children}</span>
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
    <Modal
      open
      onOpenChange={(o) => !o && props.onDone(false)}
      title={`Log ${humanize(rule.key)}`}
      description="The engine scores this against the seeded threshold — you record the readings, not the verdict."
      footer={
        <>
          <Button type="button" variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
          <Button type="submit" form="gate-result-form" disabled={busy}>
            {busy ? "Saving…" : "Log result"}
          </Button>
        </>
      }
    >
      <form id="gate-result-form" onSubmit={submit}>
        <Stack gap={4}>
          {error != null && (
            <Banner tone="danger" title="Could not log the result">
              {errorText(error)}
            </Banner>
          )}

          {isInspection ? (
            <Stack gap={2}>
              {checklist.map((c) => (
                <Checkbox
                  key={c}
                  label={c}
                  checked={checks[c]}
                  onCheckedChange={(v) => setChecks({ ...checks, [c]: v === true })}
                />
              ))}
            </Stack>
          ) : (
            <Stack gap={3}>
              {readings.map((r, i) => (
                <Row key={i}>
                  <Field label="Location" className={styles.grow}>
                    <Input value={r.location} placeholder="e.g. panel-A"
                      onChange={(e) => {
                        const next = [...readings];
                        next[i] = { ...r, location: e.target.value };
                        setReadings(next);
                      }} />
                  </Field>
                  <Field label="Value" className={styles.grow}>
                    <Input type="number" step="any" value={r.value} required
                      onChange={(e) => {
                        const next = [...readings];
                        next[i] = { ...r, value: e.target.value };
                        setReadings(next);
                      }} />
                  </Field>
                </Row>
              ))}
              <div>
                <Button type="button" variant="ghost" size="compact"
                  onClick={() => setReadings([...readings, { location: "", value: "" }])}>
                  <Plus size={15} aria-hidden="true" />
                  Add reading
                </Button>
              </div>
            </Stack>
          )}

          <Field label="Notes">
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
        </Stack>
      </form>
    </Modal>
  );
}

const REPORT_TYPES = [
  "change", "issue", "ncr", "capa", "rfi", "missing_information", "qa",
] as const;

const DEFAULT_REPORT_TYPE = "__default";

function RejectModal(props: {
  open: boolean; projectId: string; order: number; onDone: (ok: boolean) => void;
}) {
  const [comment, setComment] = useState("");
  const [type, setType] = useState(DEFAULT_REPORT_TYPE);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/projects/${props.projectId}/stages/${props.order}/reject`, {
        method: "POST",
        body: { comment, report_type: type === DEFAULT_REPORT_TYPE ? null : type },
      });
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <Modal
      open={props.open}
      onOpenChange={(o) => !o && props.onDone(false)}
      title="Reject stage"
      description="Opens a typed report, increments the recovery loop, and reopens the stage for resubmission."
      footer={
        <>
          <Button type="button" variant="ghost" onClick={() => props.onDone(false)}>Cancel</Button>
          <Button type="submit" form="reject-stage-form" variant="danger" disabled={busy}>
            {busy ? "Rejecting…" : "Reject stage"}
          </Button>
        </>
      }
    >
      <form id="reject-stage-form" onSubmit={submit}>
        <Stack gap={4}>
          {error != null && (
            <Banner tone="danger" title="Could not reject the stage">
              {errorText(error)}
            </Banner>
          )}
          <Field label="Reason" required>
            <Input value={comment} onChange={(e) => setComment(e.target.value)} required
              placeholder="What must change before resubmission" />
          </Field>
          <Field label="Report type" hint="Defaults to the stage's own recovery type.">
            <Select
              value={type}
              onValueChange={setType}
              options={[
                { value: DEFAULT_REPORT_TYPE, label: "— default —" },
                ...REPORT_TYPES.map((t) => ({ value: t, label: humanize(t) })),
              ]}
            />
          </Field>
        </Stack>
      </form>
    </Modal>
  );
}
