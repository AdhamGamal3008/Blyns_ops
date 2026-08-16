// The per-stage configuration editor (docs/PROJECT_CONFIGURATIONS_PLAN.md §6 P3).
//
// Loads a configuration's CURRENT version, edits it entirely CLIENT-SIDE, and
// Save publishes the whole edited set as a new immutable version (§3 — there is
// no server-side draft, so nothing is half-saved and nobody's unsaved work is
// waiting on the server). Projects already running keep the version they pinned.
//
// D2 fixes the 9-stage skeleton: a stage's order, name and approver position are
// shown but NOT editable, because module integrations hook stage keys (G-2).

import { ChevronDown, ChevronRight, Plus, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  Banner,
  Button,
  Checkbox,
  Field,
  FormModal,
  Input,
  NativeSelect,
  Row,
  Spinner,
  Stack,
  Switch,
} from "../../shared/ui";
import styles from "./ConfigurationsSection.module.css";
import {
  type ConfigurationDetail,
  type GateCatalogEntry,
  humanize,
  SHAPE_HINT,
  SHAPE_LABEL,
  type Threshold,
  type VersionPublish,
  type WorkflowShape,
} from "./configurationTypes";

/** The editable shape of one stage while the editor is open. */
interface StageDraft {
  key: string;
  order: number;
  name: string;
  approver_role: string | null;
  documents: { key: string; label: string; blocking: boolean }[];
  quality_gates: string[];
}

/** Per-gate tuning, keyed by gate key. Only gates actually attached are sent. */
type GateDraft = Record<string, { threshold: Threshold; blocking: boolean }>;

function toDrafts(detail: ConfigurationDetail): {
  stages: StageDraft[];
  gates: GateDraft;
} {
  const stages = [...detail.stages]
    .sort((a, b) => a.order - b.order)
    .map((s) => ({
      key: s.key,
      order: s.order,
      name: s.name,
      approver_role: s.approver_role,
      documents: (s.entry_gates ?? [])
        .filter((g) => g.type === "document")
        .map((g) => ({
          key: g.key,
          label: g.label ?? humanize(g.key),
          blocking: g.blocking !== false,
        })),
      quality_gates: [...(s.quality_gates ?? [])],
    }));

  const gates: GateDraft = {};
  for (const rule of detail.gates) {
    gates[rule.key] = {
      threshold: { ...(rule.threshold ?? {}) },
      blocking: rule.blocking !== false,
    };
  }
  return { stages, gates };
}

export function ConfigurationEditor(props: {
  configuration: { id: string; name: string };
  onDone: (published: boolean) => void;
}) {
  const [detail, setDetail] = useState<ConfigurationDetail | null>(null);
  const [catalog, setCatalog] = useState<GateCatalogEntry[]>([]);
  const [stages, setStages] = useState<StageDraft[]>([]);
  const [gates, setGates] = useState<GateDraft>({});
  const [shape, setShape] = useState<WorkflowShape>("sequential");
  const [open, setOpen] = useState<string | null>(null);
  const [newGate, setNewGate] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const id = props.configuration.id;

  useEffect(() => {
    let live = true;
    api<ConfigurationDetail>(`/projects/config/configurations/${id}`)
      .then((r) => {
        if (!live) return;
        setDetail(r.data);
        setShape(r.data.workflow_shape);
        const drafts = toDrafts(r.data);
        setStages(drafts.stages);
        setGates(drafts.gates);
        setOpen(drafts.stages[0]?.key ?? null);
      })
      .catch((err) => live && setError(err));
    return () => {
      live = false;
    };
  }, [id]);

  const loadCatalog = () => {
    api<GateCatalogEntry[]>("/projects/config/gate-catalog")
      .then((r) => setCatalog(r.data))
      .catch(() => setCatalog([]));
  };
  useEffect(loadCatalog, []);

  const catalogByKey = useMemo(
    () => Object.fromEntries(catalog.map((g) => [g.key, g])),
    [catalog],
  );

  function patchStage(key: string, patch: Partial<StageDraft>) {
    setStages((prev) =>
      prev.map((s) => (s.key === key ? { ...s, ...patch } : s)),
    );
  }

  /** Attaching a catalog gate seeds its tuning from the catalog definition — the
   *  copy the publish will make (G-3), pre-filled so thresholds are editable. */
  function toggleGate(stage: StageDraft, gateKey: string) {
    const attached = stage.quality_gates.includes(gateKey);
    patchStage(stage.key, {
      quality_gates: attached
        ? stage.quality_gates.filter((k) => k !== gateKey)
        : [...stage.quality_gates, gateKey],
    });
    if (!attached && gates[gateKey] == null) {
      const source = catalogByKey[gateKey];
      setGates((prev) => ({
        ...prev,
        [gateKey]: {
          threshold: { ...(source?.threshold ?? {}) },
          blocking: source?.blocking !== false,
        },
      }));
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const attached = new Set(stages.flatMap((s) => s.quality_gates));
    const body: VersionPublish = {
      workflow_shape: shape,
      stages: stages.map((s) => ({
        key: s.key,
        entry_documents: s.documents.map((d) => ({
          key: d.key,
          label: d.label,
          blocking: d.blocking,
        })),
        quality_gates: s.quality_gates,
      })),
      gates: [...attached].map((key) => ({
        key,
        threshold: gates[key]?.threshold,
        blocking: gates[key]?.blocking,
      })),
    };
    try {
      await api(`/projects/config/configurations/${id}/versions`, {
        method: "POST",
        body,
      });
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  const nextVersion = (detail?.current_version ?? 0) + 1;

  return (
    <FormModal
      open
      onOpenChange={(o) => !o && props.onDone(false)}
      size="lg"
      title={`Edit ${props.configuration.name}`}
      description={
        detail
          ? `Saving publishes version ${nextVersion}. Projects already running keep the version they started on.`
          : "Loading…"
      }
      onSubmit={submit}
      error={error}
      errorTitle="Could not publish this version"
      busy={busy}
      submitLabel={`Publish version ${nextVersion}`}
      submitDisabled={!detail}
    >
      {!detail ? (
        <Row gap={3}>
          <Spinner />
          <span>Loading configuration…</span>
        </Row>
      ) : (
        <Stack gap={5}>
          <Field
            label="Workflow shape"
            hint={SHAPE_HINT[shape]}
          >
            <NativeSelect
              value={shape}
              onChange={(e) => setShape(e.target.value as WorkflowShape)}
              options={(["sequential", "concurrent"] as const).map((s) => ({
                value: s,
                label: SHAPE_LABEL[s],
              }))}
            />
          </Field>

          <Banner tone="info" title="The nine stages are fixed">
            A configuration tunes each stage's documents and quality gates. Stage
            names, order and approver positions stay the same so the Production,
            Inventory and Finance hand-offs keep working.
          </Banner>

          <Stack gap={3}>
            {stages.map((stage) => (
              <StageEditor
                key={stage.key}
                stage={stage}
                open={open === stage.key}
                onToggleOpen={() =>
                  setOpen(open === stage.key ? null : stage.key)
                }
                catalog={catalog}
                gates={gates}
                onPatch={(patch) => patchStage(stage.key, patch)}
                onToggleGate={(gateKey) => toggleGate(stage, gateKey)}
                onTuneGate={(gateKey, tuning) =>
                  setGates((prev) => ({
                    ...prev,
                    [gateKey]: { ...prev[gateKey], ...tuning },
                  }))
                }
                onAddGate={() => setNewGate(true)}
              />
            ))}
          </Stack>
        </Stack>
      )}

      {newGate && (
        <GateCatalogModal
          onDone={(created) => {
            setNewGate(false);
            if (created) loadCatalog();
          }}
        />
      )}
    </FormModal>
  );
}

// --- one stage ---------------------------------------------------------------

function StageEditor(props: {
  stage: StageDraft;
  open: boolean;
  onToggleOpen: () => void;
  catalog: GateCatalogEntry[];
  gates: GateDraft;
  onPatch: (patch: Partial<StageDraft>) => void;
  onToggleGate: (gateKey: string) => void;
  onTuneGate: (
    gateKey: string,
    tuning: Partial<{ threshold: Threshold; blocking: boolean }>,
  ) => void;
  onAddGate: () => void;
}) {
  const { stage } = props;
  const [docKey, setDocKey] = useState("");
  const Chevron = props.open ? ChevronDown : ChevronRight;

  function addDocument() {
    const key = docKey.trim().toLowerCase().replace(/\s+/g, "_");
    if (!key || stage.documents.some((d) => d.key === key)) return;
    props.onPatch({
      documents: [
        ...stage.documents,
        { key, label: humanize(key), blocking: true },
      ],
    });
    setDocKey("");
  }

  return (
    <div className={styles.stage}>
      <button
        type="button"
        className={styles.stageHead}
        onClick={props.onToggleOpen}
        aria-expanded={props.open}
      >
        <Chevron size={16} aria-hidden="true" />
        <span className={styles.stageOrder}>{stage.order}</span>
        <span className={styles.stageName}>{stage.name}</span>
        <span className={styles.stageSummary}>
          {stage.documents.length} doc{stage.documents.length === 1 ? "" : "s"} ·{" "}
          {stage.quality_gates.length} gate
          {stage.quality_gates.length === 1 ? "" : "s"}
        </span>
      </button>

      {props.open && (
        <div className={styles.stageBody}>
          <p className={styles.fixed}>
            Approver position:{" "}
            {stage.approver_role ? humanize(stage.approver_role) : "none (auto-advances)"}
          </p>

          <Field
            label="Entry documents"
            hint="What must be attached before this stage can move out of waiting."
          >
            <Stack gap={2}>
              {stage.documents.map((doc) => (
                <div key={doc.key} className={styles.docRow}>
                  <Input
                    aria-label={`Label for ${doc.key}`}
                    value={doc.label}
                    onChange={(e) =>
                      props.onPatch({
                        documents: stage.documents.map((d) =>
                          d.key === doc.key ? { ...d, label: e.target.value } : d,
                        ),
                      })
                    }
                  />
                  <Checkbox
                    label="Blocking"
                    checked={doc.blocking}
                    onCheckedChange={(checked) =>
                      props.onPatch({
                        documents: stage.documents.map((d) =>
                          d.key === doc.key ? { ...d, blocking: checked === true } : d,
                        ),
                      })
                    }
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="compact"
                    aria-label={`Remove ${doc.label}`}
                    onClick={() =>
                      props.onPatch({
                        documents: stage.documents.filter((d) => d.key !== doc.key),
                      })
                    }
                  >
                    <X size={14} aria-hidden="true" />
                  </Button>
                </div>
              ))}

              <Row gap={2}>
                <Input
                  aria-label={`Add a document to ${stage.name}`}
                  placeholder="e.g. insurance_certificate"
                  value={docKey}
                  onChange={(e) => setDocKey(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addDocument();
                    }
                  }}
                />
                <Button type="button" variant="secondary" size="compact" onClick={addDocument}>
                  <Plus size={14} aria-hidden="true" />
                  Add document
                </Button>
              </Row>
            </Stack>
          </Field>

          <Field
            label="Quality gates"
            hint="Measured or inspected before this stage can be approved. Tuning a
              threshold here only affects this configuration."
          >
            <Stack gap={2}>
              {props.catalog.map((entry) => {
                const attached = stage.quality_gates.includes(entry.key);
                const tuning = props.gates[entry.key];
                return (
                  <div key={entry.key} className={styles.gateBox}>
                    <Row gap={3}>
                      <Checkbox
                        label={entry.name}
                        checked={attached}
                        onCheckedChange={() => props.onToggleGate(entry.key)}
                      />
                      {entry.is_builtin ? (
                        <Badge tone="neutral">built-in</Badge>
                      ) : (
                        <Badge tone="brand">custom</Badge>
                      )}
                    </Row>

                    {attached && tuning && (
                      <>
                        <div className={styles.thresholds}>
                          {Object.entries(tuning.threshold).map(([field, value]) => (
                            <ThresholdField
                              key={field}
                              name={field}
                              value={value}
                              onChange={(next) =>
                                props.onTuneGate(entry.key, {
                                  threshold: { ...tuning.threshold, [field]: next },
                                })
                              }
                            />
                          ))}
                        </div>
                        <Switch
                          label="Blocks approval until it passes"
                          checked={tuning.blocking}
                          onCheckedChange={(checked) =>
                            props.onTuneGate(entry.key, { blocking: checked })
                          }
                        />
                      </>
                    )}
                  </div>
                );
              })}

              <Row>
                <Button type="button" variant="secondary" size="compact" onClick={props.onAddGate}>
                  <Plus size={14} aria-hidden="true" />
                  New gate
                </Button>
              </Row>
            </Stack>
          </Field>
        </div>
      )}
    </div>
  );
}

/** One field of a gate's threshold. A threshold is a free-form object whose keys
 *  differ per gate (`max_rh_pct`, `min`/`max`, `method`, `site_defined`…), so the
 *  control is chosen from the seeded value's TYPE — and editing must preserve it:
 *  writing the string "true" where the engine expects a boolean, or "75" where it
 *  expects a number, would silently stop the gate evaluating. */
function ThresholdField(props: {
  name: string;
  value: string | number | boolean;
  onChange: (next: string | number | boolean) => void;
}) {
  const { name, value } = props;

  if (typeof value === "boolean") {
    return (
      <Checkbox
        label={humanize(name)}
        checked={value}
        onCheckedChange={(checked) => props.onChange(checked === true)}
      />
    );
  }
  return (
    <Field label={humanize(name)}>
      <Input
        type={typeof value === "number" ? "number" : "text"}
        value={String(value)}
        onChange={(e) =>
          props.onChange(
            typeof value === "number"
              ? // an empty box would become NaN and poison the threshold
                (e.target.value === "" ? 0 : Number(e.target.value))
              : e.target.value,
          )
        }
      />
    </Field>
  );
}

// --- a tenant's own gate definition ------------------------------------------

export function GateCatalogModal(props: { onDone: (created: boolean) => void }) {
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState<"measurement" | "inspection">("measurement");
  const [field, setField] = useState("max");
  const [limit, setLimit] = useState("");
  const [checklist, setChecklist] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/projects/config/gate-catalog", {
        method: "POST",
        body: {
          key: key.trim().toLowerCase().replace(/\s+/g, "_"),
          name,
          type,
          ...(type === "measurement"
            ? { threshold: { [field.trim() || "max"]: Number(limit) } }
            : {
                checklist: checklist
                  .split("\n")
                  .map((l) => l.trim())
                  .filter(Boolean),
              }),
        },
      });
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
      title="New quality gate"
      description="A reusable gate definition. Attach it to any stage of any configuration."
      onSubmit={submit}
      error={error}
      errorTitle="Could not create the gate"
      busy={busy}
      submitLabel="Create gate"
    >
      <Stack gap={4}>
        <Field label="Name" required>
          <Input
            value={name}
            required
            onChange={(e) => {
              setName(e.target.value);
              if (!key) setKey(e.target.value.toLowerCase().replace(/\s+/g, "_"));
            }}
            placeholder="e.g. Adhesive open time"
          />
        </Field>
        <Field label="Key" hint="Lowercase identifier used in the API and reports." required>
          <Input value={key} required onChange={(e) => setKey(e.target.value)} />
        </Field>
        <Field label="Type">
          <NativeSelect
            value={type}
            onChange={(e) => setType(e.target.value as "measurement" | "inspection")}
            options={[
              { value: "measurement", label: "Measurement — a reading against a limit" },
              { value: "inspection", label: "Inspection — a checklist" },
            ]}
          />
        </Field>

        {type === "measurement" ? (
          <Row gap={2}>
            <Field label="Limit name">
              <Input value={field} onChange={(e) => setField(e.target.value)} />
            </Field>
            <Field label="Limit value" required>
              <Input
                type="number"
                value={limit}
                required
                onChange={(e) => setLimit(e.target.value)}
              />
            </Field>
          </Row>
        ) : (
          <Field label="Checklist" hint="One item per line." required>
            <textarea
              aria-label="Checklist"
              rows={4}
              value={checklist}
              onChange={(e) => setChecklist(e.target.value)}
            />
          </Field>
        )}
      </Stack>
    </FormModal>
  );
}
