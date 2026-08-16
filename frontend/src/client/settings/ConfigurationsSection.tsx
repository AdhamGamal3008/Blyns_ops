// Project configurations (docs/PROJECT_CONFIGURATIONS_PLAN.md §6 P3).
//
// A tenant defines named workflows — "Standard", "Flooring — ASTM",
// "Fast-track joinery" — each a versioned set of the 9 stages' documents, quality
// gates and thresholds. One is the default; a project picks its configuration at
// Stage 1 and pins that version for life.
//
// Managing these is `settings` WRITE, the same guard as the approver map next
// door (§4). A read-only viewer still sees what exists.

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  Banner,
  Button,
  CardHeader,
  DataState,
  errorText,
  Field,
  FormModal,
  Input,
  NativeSelect,
  Row,
  Stack,
} from "../../shared/ui";
import { ConfigurationEditor } from "./ConfigurationEditor";
import styles from "./ConfigurationsSection.module.css";
import {
  type ProjectConfiguration,
  SHAPE_LABEL,
} from "./configurationTypes";

const ROOT = "/projects/config/configurations";

export function ConfigurationsSection(props: { canWrite: boolean }) {
  const [configs, setConfigs] = useState<ProjectConfiguration[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<ProjectConfiguration | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<ProjectConfiguration[]>(ROOT)
      .then((r) => setConfigs(r.data))
      .catch(setError);
  }, []);

  useEffect(load, [load]);

  async function act(config: ProjectConfiguration, body: Record<string, unknown>) {
    setError(null);
    setNotice(null);
    try {
      await api(`${ROOT}/${config.id}`, { method: "PATCH", body });
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(config: ProjectConfiguration) {
    if (!window.confirm(`Delete the "${config.name}" configuration?`)) return;
    setError(null);
    setNotice(null);
    try {
      await api(`${ROOT}/${config.id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section>
      <CardHeader
        title="Project configurations"
        description="Named workflows a project can be started on. Editing one publishes a new version; projects already running keep the version they started on."
        actions={
          props.canWrite && (
            <Button size="compact" onClick={() => setCreating(true)}>
              <Plus size={15} aria-hidden="true" />
              New configuration
            </Button>
          )
        }
      />

      {notice != null && (
        <Banner tone="success" title="Published">{notice}</Banner>
      )}
      {error != null && configs != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!configs && !error}
        error={configs ? null : error}
        onRetry={load}
        isEmpty={configs?.length === 0}
        emptyTitle="No project configurations"
      >
        <div className={styles.list}>
          {(configs ?? []).map((config) => (
            <div
              key={config.id}
              className={styles.card}
              data-inactive={!config.is_active}
            >
              <Stack gap={1}>
                <Row gap={2}>
                  <span className={styles.name}>{config.name}</span>
                  {config.is_default && <Badge tone="brand">default</Badge>}
                  {config.is_system && <Badge tone="neutral">built-in</Badge>}
                  {!config.is_active && <Badge tone="warning">inactive</Badge>}
                </Row>
                <span className={styles.meta}>
                  {SHAPE_LABEL[config.workflow_shape]} · version{" "}
                  {config.current_version}
                </span>
                {config.description && (
                  <span className={styles.meta}>{config.description}</span>
                )}
              </Stack>

              {props.canWrite && (
                <div className={styles.actions}>
                  <Button
                    variant="secondary"
                    size="compact"
                    onClick={() => setEditing(config)}
                  >
                    Edit stages
                  </Button>
                  {!config.is_default && (
                    <Button
                      variant="ghost"
                      size="compact"
                      onClick={() => act(config, { is_default: true })}
                    >
                      Set default
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="compact"
                    onClick={() => act(config, { is_active: !config.is_active })}
                  >
                    {config.is_active ? "Deactivate" : "Activate"}
                  </Button>
                  {!config.is_system && (
                    <Button
                      variant="ghost"
                      size="compact"
                      onClick={() => remove(config)}
                    >
                      Delete
                    </Button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </DataState>

      {creating && (
        <NewConfigurationModal
          bases={configs ?? []}
          onDone={(created) => {
            setCreating(false);
            if (created) load();
          }}
        />
      )}

      {editing && (
        <ConfigurationEditor
          configuration={editing}
          onDone={(published) => {
            const name = editing.name;
            setEditing(null);
            if (published) {
              setNotice(`A new version of "${name}" is now live for new projects.`);
              load();
            }
          }}
        />
      )}
    </section>
  );
}

// --- create by cloning --------------------------------------------------------

/** §5 — a configuration is always created by CLONING an existing one, so a tenant
 *  starts from a working 9-stage machine rather than a blank one. */
export function NewConfigurationModal(props: {
  bases: ProjectConfiguration[];
  onDone: (created: boolean) => void;
}) {
  const fallback = props.bases.find((b) => b.is_default) ?? props.bases[0];
  const [name, setName] = useState("");
  const [base, setBase] = useState(fallback?.id ?? "");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(ROOT, {
        method: "POST",
        body: { name, base_configuration_id: base || undefined },
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
      title="New project configuration"
      description="Starts as a copy of an existing configuration — adjust its stages afterwards."
      onSubmit={submit}
      error={error}
      errorTitle="Could not create the configuration"
      busy={busy}
      submitLabel="Create configuration"
    >
      <Stack gap={4}>
        <Field label="Name" required>
          <Input
            value={name}
            required
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Flooring — ASTM"
          />
        </Field>
        <Field label="Copy from" hint="Its stages, documents and gates are copied as version 1.">
          <NativeSelect
            value={base}
            onChange={(e) => setBase(e.target.value)}
            options={props.bases.map((b) => ({
              value: b.id,
              label: `${b.name} (${SHAPE_LABEL[b.workflow_shape]})`,
            }))}
          />
        </Field>
      </Stack>
    </FormModal>
  );
}
