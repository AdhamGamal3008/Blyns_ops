// Standalone company calendar events (§1.4) — they surface on the Dashboard
// calendar as company_event, respecting visibility.

import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../../shared/ui";

interface CompanyEvent {
  id: string;
  title: string;
  start: string;
  end: string | null;
  all_day: boolean;
  visibility: string;
}

export function EventsSection(props: { canWrite: boolean }) {
  const [events, setEvents] = useState<CompanyEvent[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [title, setTitle] = useState("");
  const [start, setStart] = useState("");
  const [visibility, setVisibility] = useState("company");

  const load = useCallback(() => {
    api<CompanyEvent[]>("/settings/calendar-events")
      .then((r) => setEvents(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
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

  if (!events) return <Spinner />;

  return (
    <Card title="Company calendar events">
      <ErrorNote error={error} />
      {props.canWrite && (
        <form onSubmit={add}
          style={{ display: "flex", gap: 10, alignItems: "flex-end", marginBottom: 16 }}>
          <Field label="Title">
            <input value={title} onChange={(e) => setTitle(e.target.value)} required />
          </Field>
          <Field label="Date">
            <input type="date" value={start}
              onChange={(e) => setStart(e.target.value)} required />
          </Field>
          <Field label="Visibility">
            <select value={visibility} onChange={(e) => setVisibility(e.target.value)}>
              <option value="company">company</option>
              <option value="role">my role</option>
              <option value="owner">only me</option>
            </select>
          </Field>
          <div className="field"><Button type="submit">Add event</Button></div>
        </form>
      )}
      <table className="table">
        <thead>
          <tr><th>Title</th><th>Date</th><th>Visibility</th>{props.canWrite && <th></th>}</tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.id}>
              <td><b>{e.title}</b></td>
              <td className="muted">{new Date(e.start).toLocaleDateString()}</td>
              <td><Badge>{e.visibility}</Badge></td>
              {props.canWrite && (
                <td style={{ textAlign: "right" }}>
                  <Button variant="ghost" onClick={() => remove(e.id)}>Delete</Button>
                </td>
              )}
            </tr>
          ))}
          {events.length === 0 && (
            <tr><td colSpan={4} className="muted">No standalone events yet.</td></tr>
          )}
        </tbody>
      </table>
    </Card>
  );
}
