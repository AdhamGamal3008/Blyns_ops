// CSV import & export for any module's tab (docs/modules/CRM.md §7,
// docs/modules/INVENTORY.md §7).
//
// One bar, driven entirely by the server: both dialogs are rendered from
// `/{module}/export/{entity}/fields`, so the columns offered here can never
// drift from the columns the parser accepts, and a data set the server marks
// export-only (Inventory's derived stock levels) simply shows no Import.
//
// Import is deliberately two passes over the same file: the first reports what
// would happen and writes nothing, the second applies it. Nobody imports 400
// rows into live data without seeing the damage first.

import { Download, FileWarning, Upload } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, apiDownload, apiUpload } from "../api";
import type { CsvGrants } from "./access";
import {
  Badge,
  Banner,
  Button,
  Checkbox,
  errorText,
  Field,
  FormModal,
  Input,
  Modal,
  NativeSelect,
  Row,
  Spinner,
  Stack,
} from "../ui";
import styles from "./DataTransfer.module.css";

/** Which module owns the routes. Entity names are the server's to define, so
 *  they stay free-form strings rather than a union the UI has to keep in sync. */
export type CsvModule = "crm" | "inventory";

interface CsvFieldMeta {
  key: string;
  header: string;
  kind: string;
  required: boolean;
  choices: string[];
  importable: boolean;
  exportable: boolean;
  example: string;
  hint: string;
}

interface CsvMeta {
  entity: string;
  label: string;
  /** False for a derived data set — export it, never write it back. */
  importable: boolean;
  /** True for an immutable ledger: a repeat import adds entries, never updates. */
  append_only: boolean;
  fields: CsvFieldMeta[];
  filters: {
    status: { label: string; choices: string[] } | null;
    date_fields: { key: string; label: string }[];
    supports_search: boolean;
    supports_owner: boolean;
  };
}

interface ImportError {
  row: number;
  column: string | null;
  value: string;
  message: string;
}

interface ImportReport {
  entity: string;
  label: string;
  mode?: "validate" | "commit";
  // "committed" when written; "pending_approval" when the importer may not
  // approve this tab and the file was staged for someone who can.
  status?: "validated" | "committed" | "pending_approval";
  request_id?: string;
  file: string;
  rows: number;
  created: number;
  updated: number;
  failed: number;
  columns: string[];
  ignored_columns: string[];
  errors: ImportError[];
  errors_truncated: boolean;
}

// The spec is static per tenant, so one fetch per entity per session is plenty.
const metaCache = new Map<string, CsvMeta>();

function useCsvMeta(module: CsvModule, entity: string, enabled: boolean) {
  const cacheKey = `${module}/${entity}`;
  const [meta, setMeta] = useState<CsvMeta | null>(metaCache.get(cacheKey) ?? null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!enabled || meta) return;
    let live = true;
    api<CsvMeta>(`/${module}/export/${entity}/fields`)
      .then((r) => {
        metaCache.set(cacheKey, r.data);
        if (live) setMeta(r.data);
      })
      .catch((err) => live && setError(err));
    return () => {
      live = false;
    };
  }, [module, entity, cacheKey, enabled, meta]);

  return { meta, error };
}

export function DataTransfer(props: {
  module: CsvModule;
  entity: string;
  /** Per-tab CSV grants for the current user (shared/csv/access.ts). Export and
   *  Import each appear only when granted; an importer who cannot approve this
   *  tab submits for approval instead of writing directly. */
  csv: CsvGrants;
  /** Refresh the list once rows have actually landed. */
  onImported: () => void;
  /** Skip the Import button without asking the server — for a data set the
   *  caller already knows is derived. The server is still authoritative. */
  exportOnly?: boolean;
}) {
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  // Peek at the spec so a derived data set never offers an Import it would
  // refuse. Only fetched once either dialog has been opened.
  const { meta } = useCsvMeta(props.module, props.entity, exporting || importing);
  const canImport =
    props.csv.canImport && !props.exportOnly && (meta?.importable ?? true);
  // An importer who cannot approve this tab has the file staged for review.
  const needsApproval = canImport && !props.csv.canApprove;

  // No grants for this tab → no controls at all.
  if (!props.csv.canExport && !canImport) return null;

  return (
    <>
      {props.csv.canExport && (
        <Button variant="ghost" size="compact" onClick={() => setExporting(true)}>
          <Download size={15} aria-hidden="true" />
          Export
        </Button>
      )}
      {canImport && (
        <Button variant="ghost" size="compact" onClick={() => setImporting(true)}>
          <Upload size={15} aria-hidden="true" />
          Import
        </Button>
      )}

      {props.csv.canExport && (
        <ExportDialog
          module={props.module}
          entity={props.entity}
          open={exporting}
          onClose={() => setExporting(false)}
        />
      )}
      {canImport && (
        <ImportDialog
          module={props.module}
          entity={props.entity}
          needsApproval={needsApproval}
          open={importing}
          onClose={() => setImporting(false)}
          onImported={props.onImported}
        />
      )}
    </>
  );
}

// --- export ------------------------------------------------------------------

function ExportDialog(props: {
  module: CsvModule;
  entity: string;
  open: boolean;
  onClose: () => void;
}) {
  const { meta, error: metaError } = useCsvMeta(props.module, props.entity, props.open);
  const [selected, setSelected] = useState<string[] | null>(null);
  const [status, setStatus] = useState("");
  const [owner, setOwner] = useState("all");
  const [dateField, setDateField] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const columns = (meta?.fields ?? []).filter((f) => f.exportable);
  // Everything is ticked to begin with: the common case is "give me the lot".
  const chosen = selected ?? columns.map((f) => f.key);

  function toggle(key: string) {
    setSelected(
      chosen.includes(key) ? chosen.filter((k) => k !== key) : [...chosen, key],
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const params = new URLSearchParams();
    // Send the selection in spec order so the file's columns are predictable.
    params.set("fields", columns.filter((f) => chosen.includes(f.key)).map((f) => f.key).join(","));
    if (status) params.set("status", status);
    if (owner === "mine") params.set("owner", "mine");
    if (from || to) {
      if (dateField) params.set("date_field", dateField);
      if (from) params.set("date_from", from);
      if (to) params.set("date_to", to);
    }
    try {
      await apiDownload(
        `/${props.module}/export/${props.entity}?${params.toString()}`,
        `${props.module}-${props.entity}.csv`,
      );
      props.onClose();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const statusFilter = meta?.filters.status;

  return (
    <FormModal
      open={props.open}
      onOpenChange={(o) => !o && props.onClose()}
      title={`Export ${meta?.label ?? "records"}`}
      description="Pick the columns you want and narrow the rows down. The file downloads as CSV."
      onSubmit={submit}
      error={error ?? metaError}
      errorTitle="The export failed"
      busy={busy}
      submitLabel="Export CSV"
      busyLabel="Preparing…"
      submitDisabled={!meta || chosen.length === 0}
      size="lg"
    >
      {!meta && !metaError ? (
        <Row gap={2}>
          <Spinner />
          <span>Loading columns…</span>
        </Row>
      ) : (
        <>
          <Field
            label="Columns"
            hint={`${chosen.length} of ${columns.length} selected`}
          >
            <div>
              <Row gap={2} className={styles.columnActions}>
                <Button
                  type="button" variant="ghost" size="compact"
                  onClick={() => setSelected(columns.map((f) => f.key))}
                >
                  Select all
                </Button>
                <Button
                  type="button" variant="ghost" size="compact"
                  onClick={() => setSelected([])}
                >
                  Clear
                </Button>
              </Row>
              <div className={styles.columnGrid}>
                {columns.map((f) => (
                  <Checkbox
                    key={f.key}
                    label={f.header}
                    checked={chosen.includes(f.key)}
                    onCheckedChange={() => toggle(f.key)}
                  />
                ))}
              </div>
            </div>
          </Field>

          {statusFilter && (
            <Field label={statusFilter.label}>
              <NativeSelect
                value={status}
                onChange={(e) => setStatus(e.target.value)}
                options={[
                  { value: "", label: `Any ${statusFilter.label.toLowerCase()}` },
                  ...statusFilter.choices.map((c) => ({ value: c, label: c })),
                ]}
              />
            </Field>
          )}

          <Field label="Owner">
            <NativeSelect
              value={owner}
              onChange={(e) => setOwner(e.target.value)}
              options={[
                { value: "all", label: "Everyone" },
                { value: "mine", label: "Only mine" },
              ]}
            />
          </Field>

          <Field
            label="Date range"
            hint="Leave the dates empty to export every row."
          >
            <div className={styles.dateRow}>
              <NativeSelect
                aria-label="Date column"
                value={dateField}
                onChange={(e) => setDateField(e.target.value)}
                options={(meta?.filters.date_fields ?? []).map((d) => ({
                  value: d.key, label: d.label,
                }))}
              />
              <Input
                type="date" aria-label="From"
                value={from} onChange={(e) => setFrom(e.target.value)}
              />
              <Input
                type="date" aria-label="To"
                value={to} onChange={(e) => setTo(e.target.value)}
              />
            </div>
          </Field>
        </>
      )}
    </FormModal>
  );
}

// --- import ------------------------------------------------------------------

function csvCell(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/** The rejected rows, as a file to fix and re-upload. Built here rather than
 *  fetched: the report already holds every issue, so a round trip would only
 *  make the server render what the browser is already holding. */
function downloadErrors(report: ImportReport) {
  const rows = [
    ["Row", "Column", "Value", "Problem"],
    ...report.errors.map((e) => [
      String(e.row), e.column ?? "", e.value, e.message,
    ]),
  ];
  const text = "﻿" + rows.map((r) => r.map(csvCell).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `${report.entity}-import-errors.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** The rejected rows, in the preview and again in the result — a row can fail
 *  at either stage, and both deserve the same treatment. */
function ErrorTable(props: { report: ImportReport; title: string }) {
  const { report } = props;
  return (
    <>
      <Row gap={2} className={styles.errorHead}>
        <FileWarning size={16} aria-hidden="true" />
        <span>
          {props.title}
          {report.errors_truncated && " (first 500 shown)"}
        </span>
        <Button
          type="button" variant="ghost" size="compact"
          onClick={() => downloadErrors(report)}
        >
          Download as CSV
        </Button>
      </Row>
      <div className={styles.errorScroll}>
        <table className={styles.errorTable}>
          <caption className={styles.srOnly}>
            Rows that could not be imported
          </caption>
          <thead>
            <tr>
              <th scope="col">Row</th>
              <th scope="col">Column</th>
              <th scope="col">Value</th>
              <th scope="col">Problem</th>
            </tr>
          </thead>
          <tbody>
            {report.errors.map((e, i) => (
              <tr key={`${e.row}-${e.column}-${i}`}>
                <td>{e.row}</td>
                <td>{e.column ?? "—"}</td>
                <td>{e.value || "—"}</td>
                <td>{e.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ImportDialog(props: {
  module: CsvModule;
  entity: string;
  /** True when a commit is staged for approval rather than written directly. */
  needsApproval: boolean;
  open: boolean;
  onClose: () => void;
  onImported: () => void;
}) {
  const { meta, error: metaError } = useCsvMeta(props.module, props.entity, props.open);
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [done, setDone] = useState<ImportReport | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [withSample, setWithSample] = useState(true);

  const reset = useCallback(() => {
    setFile(null);
    setReport(null);
    setDone(null);
    setError(null);
    setBusy(false);
  }, []);

  useEffect(() => {
    if (!props.open) reset();
  }, [props.open, reset]);

  async function send(chosen: File, mode: "validate" | "commit") {
    setError(null);
    setBusy(true);
    try {
      const res = await apiUpload<ImportReport>(
        `/${props.module}/import/${props.entity}?mode=${mode}`, chosen,
      );
      if (mode === "commit") {
        setDone(res.data);
        // A staged file writes nothing yet, so there is no list to refresh.
        if (res.data.status !== "pending_approval") props.onImported();
      } else {
        setReport(res.data);
      }
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function pick(chosen: File | null) {
    setFile(chosen);
    setReport(null);
    setDone(null);
    if (chosen) void send(chosen, "validate");
  }

  const importable = (meta?.fields ?? []).filter((f) => f.importable);
  const willWrite = report ? report.created + report.updated : 0;

  const footer = done ? (
    <Button type="button" onClick={props.onClose}>Done</Button>
  ) : (
    <>
      <Button type="button" variant="ghost" onClick={props.onClose}>Cancel</Button>
      <Button
        type="button"
        disabled={busy || !file || !report || willWrite === 0}
        onClick={() => file && send(file, "commit")}
      >
        {busy
          ? "Working…"
          : report
            ? props.needsApproval
              ? `Submit ${willWrite} row${willWrite === 1 ? "" : "s"} for approval`
              : `Import ${willWrite} row${willWrite === 1 ? "" : "s"}`
            : "Import"}
      </Button>
    </>
  );

  return (
    <Modal
      open={props.open}
      onOpenChange={(o) => !o && props.onClose()}
      title={`Import ${meta?.label ?? "records"}`}
      description="Download the template, fill it in, and upload it back."
      size="lg"
      footer={footer}
    >
      <Stack gap={4}>
        {(error != null || metaError != null) && (
          <Banner tone="danger" title="That file could not be read">
            {errorText(error ?? metaError)}
          </Banner>
        )}

        {done ? (
          done.status === "pending_approval" ? (
            <Banner tone="info" title="Sent for approval">
              {done.created + done.updated} row
              {done.created + done.updated === 1 ? "" : "s"} were submitted for an
              approver to review
              {done.failed > 0
                ? `; ${done.failed} row${done.failed === 1 ? "" : "s"} with ` +
                  "problems will be left out"
                : ""}
              . Nothing is written until they approve.
            </Banner>
          ) : (
            <>
              <Banner
                tone={done.failed > 0 ? "warning" : "success"}
                title={done.failed > 0 ? "Imported with some rows skipped" : "Import complete"}
              >
                {done.created} created, {done.updated} updated
                {done.failed > 0 ? `, ${done.failed} skipped` : ""}.
              </Banner>
              {/* Some rows can only fail at the moment they are written — an
                  Inventory movement is refused for insufficient stock when it
                  claims it, which the dry run could not know. Show those here
                  rather than only in the preview. */}
              {done.errors.length > 0 && (
                <ErrorTable report={done} title="These rows were skipped" />
              )}
            </>
          )
        ) : (
          <>
            <section className={styles.step}>
              <h4 className={styles.stepTitle}>1. Start from the template</h4>
              <p className={styles.stepBody}>
                It carries exactly the headings this importer reads. Keep the
                header row, paste your data underneath, and save as CSV.
              </p>
              <Row gap={3}>
                <Button
                  type="button" variant="secondary" size="compact"
                  onClick={() =>
                    apiDownload(
                      `/${props.module}/import/${props.entity}/template?sample=${withSample}`,
                      `${props.module}-${props.entity}-template.csv`,
                    )
                  }
                >
                  <Download size={15} aria-hidden="true" />
                  Download template
                </Button>
                <Checkbox
                  label="Include an example row"
                  checked={withSample}
                  onCheckedChange={(v) => setWithSample(v === true)}
                />
              </Row>

              {importable.length > 0 && (
                <details className={styles.columnHelp}>
                  <summary>What each column expects</summary>
                  <dl className={styles.columnList}>
                    {importable.map((f) => (
                      <div key={f.key} className={styles.columnItem}>
                        <dt>
                          {f.header}
                          {f.required && <Badge tone="danger">required</Badge>}
                        </dt>
                        <dd>
                          {f.choices.length > 0
                            ? `One of: ${f.choices.join(", ")}. `
                            : ""}
                          {f.hint}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </details>
              )}
            </section>

            <section className={styles.step}>
              <h4 className={styles.stepTitle}>2. Upload the filled-in file</h4>
              <Field
                label="CSV file"
                hint="Nothing is saved until you confirm on the next step."
              >
                <Input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(e) => pick(e.target.files?.[0] ?? null)}
                />
              </Field>
              {busy && !report && (
                <Row gap={2}>
                  <Spinner />
                  <span>Checking your file…</span>
                </Row>
              )}
            </section>

            {report && (
              <section className={styles.step}>
                <h4 className={styles.stepTitle}>3. Check, then confirm</h4>
                <Row gap={3} className={styles.counts}>
                  <Badge tone="success">{report.created} to create</Badge>
                  <Badge tone="info">{report.updated} to update</Badge>
                  <Badge tone={report.failed > 0 ? "danger" : "neutral"}>
                    {report.failed} with problems
                  </Badge>
                </Row>
                {props.needsApproval && (
                  <Banner tone="info" title="This import needs approval">
                    You can prepare this import, but the changes take effect only
                    once an approver signs off. Submitting sends the file for
                    review — nothing is written yet.
                  </Banner>
                )}
                <p className={styles.stepBody}>
                  {meta?.append_only
                    ? "These are ledger entries, so importing this file again " +
                      "records the movements a second time rather than updating " +
                      "the first. Stock is checked as each row is posted."
                    : "Rows are matched on their key column, so re-importing a " +
                      "file updates the same records instead of duplicating " +
                      "them. A blank cell leaves the stored value alone."}
                </p>

                {report.ignored_columns.length > 0 && (
                  <Banner tone="warning" title="Some columns were ignored">
                    {report.ignored_columns.join(", ")} — check the spelling
                    against the template if you meant to import them.
                  </Banner>
                )}

                {report.errors.length > 0 && (
                  <ErrorTable report={report} title="These rows will be skipped" />
                )}
              </section>
            )}
          </>
        )}
      </Stack>
    </Modal>
  );
}
