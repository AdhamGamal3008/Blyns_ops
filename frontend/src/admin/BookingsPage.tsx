// Admin "Discovery Sessions" — the leads captured by the landing page's booking
// form. List (VIEW masks contact details), a detail drawer (READ), and a status
// pipeline + notes (WRITE). Gated on the `leads` resource; every write is audited
// server-side.

import { useCallback, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../shared/api";
import { PageHeader } from "../shared/shell";
import type {
  AdminMe,
  DiscoveryBooking,
  DiscoveryBookingStatus,
} from "../shared/types";
import {
  Badge,
  type BadgeTone,
  Banner,
  Button,
  DataState,
  DataTable,
  type DataTableColumn,
  errorText,
  Field,
  NativeSelect,
  Row,
  Sheet,
  Stack,
  Textarea,
} from "../shared/ui";
import styles from "./BookingsPage.module.css";

const STATUS_META: Record<DiscoveryBookingStatus, { label: string; tone: BadgeTone }> = {
  new: { label: "New", tone: "info" },
  contacted: { label: "Contacted", tone: "warning" },
  scheduled: { label: "Scheduled", tone: "brand" },
  closed: { label: "Closed", tone: "neutral" },
};

const INDUSTRY_LABELS: Record<string, string> = {
  interior_fit_out: "Interior Fit-Out",
  flooring: "Flooring",
  wall_cladding: "Wall Cladding",
  custom_furniture: "Custom Furniture",
  general_contractor: "General Contractor",
  other: "Other",
};

const STATUS_FILTER_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "new", label: "New" },
  { value: "contacted", label: "Contacted" },
  { value: "scheduled", label: "Scheduled" },
  { value: "closed", label: "Closed" },
];

const STATUS_OPTIONS = STATUS_FILTER_OPTIONS.slice(1);

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric", month: "short", day: "numeric",
  });
}
function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium", timeStyle: "short",
  });
}

export function BookingsPage() {
  const me = useOutletContext<AdminMe>();
  const level = me.role.permissions.leads ?? 0;
  const canRead = level >= 2;
  const canWrite = level >= 3;

  const [bookings, setBookings] = useState<DiscoveryBooking[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<DiscoveryBooking | null>(null);

  const load = useCallback(() => {
    const q = statusFilter ? `&status=${statusFilter}` : "";
    api<DiscoveryBooking[]>(`/admin/discovery-bookings?page_size=100${q}`, { realm: "admin" })
      .then((res) => setBookings(res.data))
      .catch(setError);
  }, [statusFilter]);

  useEffect(load, [load]);

  async function openDetail(row: DiscoveryBooking) {
    setError(null);
    try {
      const res = await api<DiscoveryBooking>(
        `/admin/discovery-bookings/${row.id}`, { realm: "admin" },
      );
      setSelected(res.data);
    } catch (err) {
      setError(err);
    }
  }

  const columns: DataTableColumn<DiscoveryBooking>[] = [
    { key: "company", header: "Company", accessor: (b) => <b>{b.company}</b> },
    {
      key: "contact",
      header: "Contact",
      accessor: (b) =>
        b.full_name ? (
          <span className={styles.contact}>
            {b.full_name}
            <span className={styles.contactEmail}>{b.work_email}</span>
          </span>
        ) : (
          <span className={styles.muted}>—</span>
        ),
    },
    {
      key: "industry",
      header: "Field",
      accessor: (b) => INDUSTRY_LABELS[b.industry] ?? b.industry,
    },
    {
      key: "status",
      header: "Status",
      accessor: (b) => (
        <Badge tone={STATUS_META[b.status].tone}>{STATUS_META[b.status].label}</Badge>
      ),
      sortValue: (b) => b.status,
    },
    {
      key: "created",
      header: "Received",
      accessor: (b) => fmtDate(b.created_at),
      sortValue: (b) => b.created_at,
    },
  ];

  return (
    <Stack>
      <PageHeader
        title="Discovery Sessions"
        description="Booking requests from the marketing site."
        actions={
          <NativeSelect
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            options={STATUS_FILTER_OPTIONS}
            aria-label="Filter by status"
          />
        }
      />

      {error != null && bookings != null && (
        <Banner tone="danger" title="Something went wrong">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!bookings && !error}
        error={bookings ? null : error}
        onRetry={load}
        isEmpty={bookings?.length === 0}
        emptyTitle="No bookings yet"
        emptyDescription="Discovery-session requests from the landing page will appear here."
      >
        <DataTable
          data={bookings ?? []}
          columns={columns}
          getRowId={(b) => b.id}
          searchable={(bookings?.length ?? 0) > 8}
          onRowClick={canRead ? openDetail : undefined}
        />
      </DataState>

      {!canRead && (
        <p className={styles.hint}>
          View-only access — contact details are hidden and rows can't be opened.
        </p>
      )}

      {selected && (
        <BookingDetail
          booking={selected}
          canWrite={canWrite}
          onClose={() => setSelected(null)}
          onChanged={(updated) => {
            setSelected(updated);
            load();
          }}
        />
      )}
    </Stack>
  );
}

function BookingDetail(props: {
  booking: DiscoveryBooking;
  canWrite: boolean;
  onClose: () => void;
  onChanged: (b: DiscoveryBooking) => void;
}) {
  const { booking, canWrite } = props;
  const [status, setStatus] = useState<DiscoveryBookingStatus>(booking.status);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function patch(body: { status?: string; note?: string }) {
    setBusy(true);
    setError(null);
    try {
      const res = await api<DiscoveryBooking>(
        `/admin/discovery-bookings/${booking.id}`,
        { method: "PATCH", body, realm: "admin" },
      );
      props.onChanged(res.data);
      setNote("");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      open
      onOpenChange={(o) => !o && props.onClose()}
      title={booking.company}
      description={booking.full_name}
    >
      <Stack gap={4}>
        {error != null && <Banner tone="danger">{errorText(error)}</Banner>}

        <dl className={styles.details}>
          <Detail label="Email" value={booking.work_email} />
          <Detail label="Phone" value={booking.phone} />
          <Detail label="Field" value={INDUSTRY_LABELS[booking.industry] ?? booking.industry} />
          <Detail label="Company size" value={booking.company_size} />
          <Detail label="Preferred" value={booking.preferred_at ? fmtDateTime(booking.preferred_at) : null} />
          <Detail label="Received" value={fmtDateTime(booking.created_at)} />
        </dl>

        {booking.message && (
          <div>
            <div className={styles.detailLabel}>Message</div>
            <p className={styles.message}>{booking.message}</p>
          </div>
        )}

        {canWrite && (
          <div className={styles.actions}>
            <Field label="Status">
              <Row gap={2} className={styles.statusRow}>
                <NativeSelect
                  value={status}
                  onChange={(e) => setStatus(e.target.value as DiscoveryBookingStatus)}
                  options={STATUS_OPTIONS}
                />
                <Button
                  onClick={() => patch({ status })}
                  loading={busy}
                  disabled={busy || status === booking.status}
                >
                  Update
                </Button>
              </Row>
            </Field>
            <Field label="Add a note">
              <Textarea
                rows={2}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Log a call, next step, or context."
              />
            </Field>
            <Button
              variant="secondary"
              onClick={() => patch({ note })}
              disabled={busy || !note.trim()}
              loading={busy}
            >
              Add note
            </Button>
          </div>
        )}

        {booking.notes && booking.notes.length > 0 && (
          <div>
            <div className={styles.detailLabel}>Notes</div>
            <ul className={styles.notes}>
              {booking.notes.map((n, i) => (
                <li key={i}>
                  <span>{n.text}</span>
                  <span className={styles.noteAt}>{fmtDateTime(n.at)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Stack>
    </Sheet>
  );
}

function Detail(props: { label: string; value?: string | null }) {
  return (
    <>
      <dt className={styles.detailLabel}>{props.label}</dt>
      <dd className={styles.detailValue}>{props.value || "—"}</dd>
    </>
  );
}
