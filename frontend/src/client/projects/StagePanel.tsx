// One stage's control surface (§4/§5/§6/§8): entry documents, physical gates,
// automated tasks, and the submit → approve / reject flow. Every mutation
// refreshes both this panel and the parent timeline/budget.

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, apiDownload, apiUpload } from "../../shared/api";
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
  FormModal,
  Input,
  Modal,
  Row,
  Select,
  Stack,
} from "../../shared/ui";
import {
  STAGE_TONE, humanize,
  type DeliverableSource, type DocumentRef, type EntryGate, type GateRule,
  type StageDetail, type ValidationCheck,
} from "./types";
import styles from "./StagePanel.module.css";

const isHttp = (s?: string | null) => !!s && /^https?:\/\//i.test(s);

const HANDOVER_STAGE_KEY = "final_inspection_handover";

export function StagePanel(props: {
  projectId: string;
  order: number;
  canWrite: boolean;
  canApprove: boolean;
  canWaive: boolean;
  onChanged: () => void;
}) {
  const { projectId, order, canWrite, canApprove, canWaive } = props;
  const [detail, setDetail] = useState<StageDetail | null>(null);
  const [gateRules, setGateRules] = useState<Record<string, GateRule>>({});
  const [error, setError] = useState<unknown>(null);
  const [notReached, setNotReached] = useState(false);
  const [busy, setBusy] = useState(false);
  const [validation, setValidation] = useState<ValidationCheck[] | null>(null);
  const [logging, setLogging] = useState<GateRule | null>(null);
  const [waiving, setWaiving] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [attaching, setAttaching] = useState<EntryGate | null>(null);

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
  // v2.0 Stage 2 · Site Survey has no approver — it advances on submit.
  const autoAdvance = definition.auto_advance || definition.approver_role == null;
  const isHandover = definition.key === HANDOVER_STAGE_KEY;
  const checklistDone = new Set(instance.checklist_done ?? []);

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
  const refByGate = new Map(
    (instance.document_refs ?? []).map((r) => [r.gate_key, r]),
  );
  const markSupplied = (gate: EntryGate) =>
    act(() => api(
      `/projects/${projectId}/stages/${order}/documents/${gate.key}`,
      { method: "POST", body: {} },
    ));

  return (
    <Card>
      <CardHeader
        title={`Stage ${definition.order} · ${definition.name}`}
        description={
          <>
            {autoAdvance ? (
              <b>Auto-advances on completion · no approval required</b>
            ) : (
              <>Approver <b>{humanize(definition.approver_role ?? "—")}</b></>
            )}
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
              return (
                <ItemRow
                  key={g.key}
                  label={humanize(g.key)}
                  hint={g.type === "dependency"
                    ? `phase · ${humanize(g.depends_on)}` : undefined}
                >
                  {/* the attached evidence — openable by anyone who can see the
                      stage, so an approver can review before signing off */}
                  {ref && (
                    <Evidence projectId={projectId} reference={ref} onError={setError} />
                  )}
                  {supplied.has(g.key) ? (
                    <Badge tone="success">supplied</Badge>
                  ) : !canWrite ? (
                    <Badge tone="warning">missing</Badge>
                  ) : g.type === "document" ? (
                    // a document gate is satisfied only by attaching evidence
                    <Button variant="ghost" size="compact" disabled={busy}
                      onClick={() => setAttaching(g)}>Attach</Button>
                  ) : (
                    // a phase gate carries no file — mark it directly
                    <Button variant="ghost" size="compact" disabled={busy}
                      onClick={() => markSupplied(g)}>Mark supplied</Button>
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
              const blocking = gateRules[key]?.blocking !== false;
              const passing = !!result?.passed;
              return (
                <ItemRow key={key} label={humanize(key)}
                  hint={result?.waived ? `waived · ${result.reason ?? ""}` : undefined}>
                  {result?.waived
                    ? <Badge tone="info">waived</Badge>
                    : result
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
                  {/* SOP §3: only the project_director may waive a hard gate */}
                  {canWaive && blocking && !passing && (
                    <Button variant="ghost" size="compact" disabled={busy}
                      onClick={() => setWaiving(key)}>Waive</Button>
                  )}
                </ItemRow>
              );
            })}
          </Section>
        )}

        {/* v2.0 Stage 6 · Factory Release checklist (§5-C): all four sections
            must be complete before the single release approval */}
        {(definition.release_checklist?.length ?? 0) > 0 && (
          <Section title="Release checklist">
            {definition.release_checklist!.map((section) => {
              const done = checklistDone.has(section);
              return (
                <ItemRow key={section} label={humanize(section)}>
                  <Badge tone={done ? "success" : "neutral"}>
                    {done ? "complete" : "pending"}
                  </Badge>
                  {canWrite && (
                    <Button variant="ghost" size="compact" disabled={busy}
                      onClick={() => act(() => api(
                        `/projects/${projectId}/stages/${order}/checklist/${section}`,
                        { method: "POST", body: { complete: !done } }))}>
                      {done ? "Reopen" : "Mark complete"}
                    </Button>
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
            <Button disabled={busy} onClick={submit}>
              {autoAdvance ? "Complete stage" : "Submit for approval"}
            </Button>
          )}
          {/* SOP §9: on the handover stage, a written client acceptance lets an
              open snag proceed to handover */}
          {isHandover && canWrite && status !== "approved" && (
            <Button variant="secondary" disabled={busy}
              onClick={() => setAccepting(true)}>Record client acceptance</Button>
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
      {attaching && (
        <AttachModal projectId={projectId} order={order} gate={attaching}
          onDone={(ok) => { setAttaching(null); if (ok) refresh(); }} />
      )}
      {waiving && (
        <WaiveModal projectId={projectId} order={order} gateKey={waiving}
          onDone={(ok) => { setWaiving(null); if (ok) refresh(); }} />
      )}
      <ClientAcceptanceModal open={accepting} projectId={projectId}
        onDone={(ok) => { setAccepting(false); if (ok) refresh(); }} />
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

/** The evidence attached to a document gate, as an openable link. Rendered for
 *  every viewer — an approver must be able to review it before signing off. */
function Evidence(props: {
  projectId: string; reference: DocumentRef; onError: (e: unknown) => void;
}) {
  const { reference: ref } = props;
  if (ref.source_type === "upload") {
    return (
      <Button
        variant="ghost"
        size="compact"
        onClick={async () => {
          try {
            await apiDownload(
              `/projects/${props.projectId}/deliverables/${ref.deliverable_id}/download`,
              ref.file_ref ?? ref.title,
            );
          } catch (e) {
            props.onError(e);
          }
        }}
      >
        {ref.title}
      </Button>
    );
  }
  if (isHttp(ref.file_ref)) {
    return (
      <a className={styles.refLink} href={ref.file_ref!} target="_blank" rel="noreferrer">
        {ref.title}
      </a>
    );
  }
  return <span className={styles.note}>{ref.title}</span>;
}

/** Attach what a document gate requires — a file or a URL. The gate already
 *  says what the document is and which stage it belongs to, so this asks for
 *  neither a kind nor a stage. */
function AttachModal(props: {
  projectId: string; order: number; gate: EntryGate; onDone: (ok: boolean) => void;
}) {
  const [source, setSource] = useState<DeliverableSource>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      let body: Record<string, unknown>;
      if (source === "upload") {
        if (!file) throw new Error("Choose a file to attach.");
        const up = await apiUpload<{ file_id: string }>(
          `/projects/${props.projectId}/deliverables/files`, file);
        body = { source_type: "upload", file_id: up.data.file_id };
      } else {
        if (!url.trim()) throw new Error("Enter a URL to reference.");
        body = { source_type: "url", file_ref: url.trim() };
      }
      await api(
        `/projects/${props.projectId}/stages/${props.order}/documents/${props.gate.key}/attach`,
        { method: "POST", body },
      );
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <FormModal
      open
      onOpenChange={(o) => !o && props.onDone(false)}
      title={`Attach ${humanize(props.gate.key)}`}
      description="Upload the file or link to it — the stage already defines what this document is."
      onSubmit={submit}
      error={error}
      errorTitle="Could not attach the document"
      busy={busy}
      submitLabel="Attach"
    >
      <Field label="Source">
        <Select
          value={source}
          onValueChange={(v) => setSource(v as DeliverableSource)}
          options={[
            { value: "upload", label: "Upload a file" },
            { value: "url", label: "Reference a URL" },
          ]}
        />
      </Field>
      {source === "upload" ? (
        <Field label="File" required>
          <input className={styles.fileInput} type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </Field>
      ) : (
        <Field label="URL" required>
          <Input value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder="https://…" />
        </Field>
      )}
    </FormModal>
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

/** SOP §3 — a director's written waiver of a hard gate. Recorded as a passing
 *  gate result and surfaced in the Stage-9 handover defence file. */
function WaiveModal(props: {
  projectId: string; order: number; gateKey: string; onDone: (ok: boolean) => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(
        `/projects/${props.projectId}/stages/${props.order}/gates/${props.gateKey}/waive`,
        { method: "POST", body: { reason } },
      );
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <FormModal
      open
      onOpenChange={(o) => !o && props.onDone(false)}
      title={`Waive ${humanize(props.gateKey)}`}
      description="A director's written waiver clears this hard gate. It is recorded on the project and rides in the handover defence file."
      onSubmit={submit}
      error={error}
      errorTitle="Could not waive the gate"
      busy={busy}
      submitLabel="Waive gate"
    >
      <Field label="Reason" required>
        <Input value={reason} onChange={(e) => setReason(e.target.value)} required
          placeholder="Why this hard gate is being waived" />
      </Field>
    </FormModal>
  );
}

/** SOP §9 — a written client acceptance so an open snag does not block the
 *  Stage-9 handover. The snag stays on record; the acceptance is stored too. */
function ClientAcceptanceModal(props: {
  open: boolean; projectId: string; onDone: (ok: boolean) => void;
}) {
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/projects/${props.projectId}/client-acceptance`, {
        method: "POST", body: { note },
      });
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <FormModal
      open={props.open}
      onOpenChange={(o) => !o && props.onDone(false)}
      title="Record client acceptance"
      description="A written client acceptance lets the handover proceed with an open snag (SOP §9). The snag stays on record."
      onSubmit={submit}
      error={error}
      errorTitle="Could not record the acceptance"
      busy={busy}
      submitLabel="Record acceptance"
    >
      <Field label="What the client accepted" required>
        <Input value={note} onChange={(e) => setNote(e.target.value)} required
          placeholder="e.g. Client accepts the 4mm reveal at the door head" />
      </Field>
    </FormModal>
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
