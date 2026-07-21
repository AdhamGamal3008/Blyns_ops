// Standalone company calendar events (§1.4) — they surface on the Dashboard
// calendar as company_event, respecting visibility.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  Banner,
  Button,
  Card,
  CardHeader,
  DataState,
  DataTable,
  type DataTableColumn,
  errorText,
  Field,
  Input,
  Row,
  Select,
  Stack,
} from "../../shared/ui";
import styles from "./EventsSection.module.css";

interface CompanyEvent {
  id: string;
  title: string;
  start: string;
  end: string | null;
  all_day: boolean;
  visibility: string;
}

const VISIBILITIES = [
  { value: "company", label: "Whole company" },
  { value: "role", label: "My role" },
  { value: "owner", label: "Only me" },
];

export function EventsSection(props: { canWrite: boolean }) {
  const [events, setEvents] = useState<CompanyEvent[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [title, setTitle] = useState("");
  const [start, setStart] = useState("");
  const [visibility, setVisibility] = useState("company");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<CompanyEvent[]>("/settings/calendar-events")
      .then((r) => setEvents(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/settings/calendar-events", {
        method: "POST",
        body: { title, start: new Date(start).toISOString(), visibility },
      });
      setTitle("");
      setStart("");
      load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setError(null);
    try {
      await api(`/settings/calendar-events/${id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  const columns: DataTableColumn<CompanyEvent>[] = [
    { key: "title", header: "Title", sortable: true, accessor: (e) => <b>{e.title}</b> },
    {
      key: "start",
      header: "Date",
      sortable: true,
      accessor: (e) => new Date(e.start).toLocaleDateString(),
      sortValue: (e) => e.start,
    },
    {
      key: "visibility",
      header: "Visibility",
      sortable: true,
      accessor: (e) => <Badge tone="neutral">{e.visibility}</Badge>,
      sortValue: (e) => e.visibility,
    },
    ...(props.canWrite
      ? [{
          key: "actions",
          header: "",
          accessor: (e: CompanyEvent) => (
            <Button variant="ghost" size="compact" onClick={() => remove(e.id)}>Delete</Button>
          ),
        }]
      : []),
  ];

  return (
    <Stack gap={4}>
      <CardHeader
        title="Company calendar events"
        description="These appear on everyone's dashboard calendar, subject to visibility."
      />

      {error != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      {props.canWrite && (
        <Card>
          {/* Adding an event is a two-field job — inline beats a dialog. */}
          <form onSubmit={add}>
            <Row gap={3}>
              <Field label="Title" className={styles.grow}>
                <Input value={title} onChange={(e) => setTitle(e.target.value)} required />
              </Field>
              <Field label="Date">
                <Input type="date" value={start}
                  onChange={(e) => setStart(e.target.value)} required />
              </Field>
              <Field label="Visibility">
                <Select value={visibility} onValueChange={setVisibility} options={VISIBILITIES} />
              </Field>
              <Button type="submit" disabled={busy}>{busy ? "Adding…" : "Add event"}</Button>
            </Row>
          </form>
        </Card>
      )}

      <DataState
        loading={!events && !error}
        error={events ? null : error}
        onRetry={load}
        isEmpty={events?.length === 0}
        emptyTitle="No standalone events yet"
      >
        <DataTable
          data={events ?? []}
          columns={columns}
          getRowId={(e) => e.id}
          searchPlaceholder="Search events…"
        />
      </DataState>
    </Stack>
  );
}
