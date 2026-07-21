// Typed exception reports (§3.8): Missing Info / Issue / Change / NCR / CAPA /
// RFI / QA. Resolving the last open report on a held project clears the hold
// (§4), so a resolve refreshes the parent too.

import { Plus } from "lucide-react";
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
  Row,
  Select,
} from "../../shared/ui";
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

  const open = (items ?? []).filter(
    (r) => r.status === "open" || r.status === "in_progress",
  ).length;

  const columns: DataTableColumn<Report>[] = [
    { key: "title", header: "Title", sortable: true, accessor: (r) => <b>{r.title}</b>, sortValue: (r) => r.title },
    {
      key: "type",
      header: "Type",
      sortable: true,
      accessor: (r) => <Badge tone="neutral">{humanize(r.type)}</Badge>,
      sortValue: (r) => r.type,
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      accessor: (r) => <Badge tone={REPORT_TONE[r.status]}>{r.status.replace("_", " ")}</Badge>,
      sortValue: (r) => r.status,
    },
    ...(props.canWrite
      ? [{
          key: "actions",
          header: "",
          accessor: (r: Report) =>
            r.status === "open" || r.status === "in_progress" ? (
              <Row gap={2}>
                {r.status === "open" && (
                  <Button variant="ghost" size="compact" onClick={() => setStatus(r, "in_progress")}>
                    Start
                  </Button>
                )}
                <Button variant="ghost" size="compact" onClick={() => setStatus(r, "resolved")}>
                  Resolve
                </Button>
              </Row>
            ) : null,
        }]
      : []),
  ];

  return (
    <section>
      <CardHeader
        title="Reports"
        description={
          items ? `${open} open of ${items.length} raised` : "Typed exception reports"
        }
        actions={
          props.canWrite && (
            <Button size="compact" onClick={() => setCreating(true)}>
              <Plus size={15} aria-hidden="true" />
              New report
            </Button>
          )
        }
      />

      {error != null && items != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!items && !error}
        error={items ? null : error}
        onRetry={load}
        isEmpty={items?.length === 0}
        emptyTitle="No reports"
        emptyDescription="Nothing has gone wrong on this project yet."
      >
        <DataTable
          data={items ?? []}
          columns={columns}
          getRowId={(r) => r.id}
          searchPlaceholder="Search reports…"
        />
      </DataState>

      <ReportModal
        open={creating}
        projectId={props.projectId}
        onDone={(ok) => { setCreating(false); if (ok) load(); }}
      />
    </section>
  );
}

function ReportModal(props: {
  open: boolean; projectId: string; onDone: (ok: boolean) => void;
}) {
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
    <FormModal
      open={props.open}
      onOpenChange={(o) => !o && props.onDone(false)}
      title="New report"
      onSubmit={submit}
      error={error}
      errorTitle="Could not create the report"
      busy={busy}
      submitLabel="Create"
    >
      <Field label="Type">
        <Select
          value={type}
          onValueChange={(v) => setType(v as ReportType)}
          options={TYPES.map((t) => ({ value: t, label: humanize(t) }))}
        />
      </Field>
      <Field label="Title" required>
        <Input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </Field>
    </FormModal>
  );
}
