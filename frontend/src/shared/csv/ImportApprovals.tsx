// Per-module CSV import approvals (docs/modules/SETTINGS.md §1.3).
//
// An importer who cannot approve a tab has their commit staged; this is where an
// approver acts on it. The card shows two things and appears only when there is
// something in either:
//
//   * Pending approvals — staged imports for tabs the viewer can approve, with
//     Approve / Reject / download-the-file. Approval commits server-side, where
//     the file is re-validated against current data.
//   * My requests — the viewer's own staged imports and how they were decided.
//
// Visibility mirrors the grants (shared/csv/access.ts); the server re-checks
// every action regardless.

import { Download } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, apiDownload } from "../api";
import { timeAgo } from "../format";
import type { ImportRequest } from "../types";
import type { ClientMe } from "../types";
import {
  Badge,
  Banner,
  Button,
  Card,
  CardHeader,
  errorText,
  Field,
  FormModal,
  Spinner,
  Stack,
  Textarea,
} from "../ui";
import { canApproveModule, canImportModule } from "./access";
import type { CsvModule } from "./DataTransfer";
import styles from "./ImportApprovals.module.css";

interface ApprovalResult {
  created: number;
  updated: number;
  failed: number;
}

type Note = { tone: "success" | "warning" | "danger"; text: string };

export function ImportApprovals(props: { me: ClientMe; module: CsvModule }) {
  const { me, module } = props;
  const canApprove = canApproveModule(me, module);
  const canTrack = canImportModule(me, module);

  const [inbox, setInbox] = useState<ImportRequest[]>([]);
  const [mine, setMine] = useState<ImportRequest[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<Note | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<ImportRequest | null>(null);

  const load = useCallback(() => {
    setError(null);
    if (canApprove) {
      api<ImportRequest[]>(`/${module}/import-requests`)
        .then((r) => setInbox(r.data))
        .catch(setError);
    }
    if (canTrack) {
      api<ImportRequest[]>(`/${module}/import-requests?mine=true`)
        .then((r) => setMine(r.data))
        .catch(setError);
    }
  }, [module, canApprove, canTrack]);

  useEffect(load, [load]);

  if (!canApprove && !canTrack) return null;

  const pending = inbox.filter((r) => r.status === "pending");
  // Stay out of the way until there is something to act on or follow up.
  if (pending.length === 0 && mine.length === 0 && note == null) return null;

  async function approve(req: ImportRequest) {
    setBusyId(req.id);
    setNote(null);
    try {
      const res = await api<ApprovalResult>(
        `/${module}/import-requests/${req.id}/approve`,
        { method: "POST" },
      );
      const r = res.data;
      setNote({
        tone: r.failed > 0 ? "warning" : "success",
        text:
          `Approved ${req.filename ?? "the import"}: ${r.created} created, ` +
          `${r.updated} updated${r.failed > 0 ? `, ${r.failed} skipped` : ""}.`,
      });
      load();
    } catch (err) {
      setError(err);
    } finally {
      setBusyId(null);
    }
  }

  async function reject(req: ImportRequest, reason: string) {
    setBusyId(req.id);
    try {
      await api(`/${module}/import-requests/${req.id}/reject`, {
        method: "POST",
        body: { reason },
      });
      setNote({ tone: "danger", text: `Rejected ${req.filename ?? "the import"}.` });
      setRejecting(null);
      load();
    } catch (err) {
      setError(err);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card>
      <CardHeader
        title="CSV imports"
        description="Imports waiting on a sign-off, and the ones you have submitted."
        actions={
          <Button variant="ghost" size="compact" onClick={load}>
            Refresh
          </Button>
        }
      />

      <Stack gap={4}>
        {note && (
          <Banner tone={note.tone} title="Done" onDismiss={() => setNote(null)}>
            {note.text}
          </Banner>
        )}
        {error != null && (
          <Banner tone="danger" title="That action failed">
            {errorText(error)}
          </Banner>
        )}

        {canApprove && (
          <div className={styles.group}>
            <p className={styles.groupTitle}>
              Pending approval ({pending.length})
            </p>
            {pending.length === 0 ? (
              <p className={styles.sub}>Nothing is waiting for your approval.</p>
            ) : (
              <div className={styles.list}>
                {pending.map((req) => (
                  <div key={req.id} className={styles.row}>
                    <div className={styles.meta}>
                      <span className={styles.file}>{req.filename ?? "import.csv"}</span>
                      <span className={styles.sub}>
                        {req.entity} · {req.requested_by_name ?? "someone"}
                        {req.requested_at ? ` · ${timeAgo(req.requested_at)}` : ""}
                      </span>
                    </div>
                    <div className={styles.counts}>
                      <Badge tone="success">{req.preview.created ?? 0} to create</Badge>
                      <Badge tone="info">{req.preview.updated ?? 0} to update</Badge>
                      {(req.preview.failed ?? 0) > 0 && (
                        <Badge tone="danger">{req.preview.failed} with problems</Badge>
                      )}
                    </div>
                    <div className={styles.actions}>
                      <Button
                        variant="ghost"
                        size="compact"
                        onClick={() =>
                          apiDownload(
                            `/${module}/import-requests/${req.id}/file`,
                            req.filename ?? "import.csv",
                          )
                        }
                      >
                        <Download size={15} aria-hidden="true" />
                        File
                      </Button>
                      <Button
                        variant="secondary"
                        size="compact"
                        disabled={busyId === req.id}
                        onClick={() => setRejecting(req)}
                      >
                        Reject
                      </Button>
                      <Button
                        size="compact"
                        disabled={busyId === req.id}
                        onClick={() => approve(req)}
                      >
                        {busyId === req.id ? <Spinner size="sm" /> : "Approve"}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {canTrack && mine.length > 0 && (
          <div className={styles.group}>
            <p className={styles.groupTitle}>My requests</p>
            <div className={styles.list}>
              {mine.map((req) => (
                <div key={req.id} className={styles.row}>
                  <div className={styles.meta}>
                    <span className={styles.file}>{req.filename ?? "import.csv"}</span>
                    <span className={styles.sub}>
                      {req.entity}
                      {req.requested_at ? ` · ${timeAgo(req.requested_at)}` : ""}
                      {req.status === "rejected" && req.reject_reason
                        ? ` · “${req.reject_reason}”`
                        : ""}
                    </span>
                  </div>
                  <div className={styles.actions}>
                    <Badge tone={STATUS_TONE[req.status]}>{STATUS_LABEL[req.status]}</Badge>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Stack>

      {rejecting && (
        <RejectModal
          request={rejecting}
          busy={busyId === rejecting.id}
          onCancel={() => setRejecting(null)}
          onReject={(reason) => reject(rejecting, reason)}
        />
      )}
    </Card>
  );
}

const STATUS_LABEL: Record<ImportRequest["status"], string> = {
  pending: "Awaiting approval",
  approved: "Approved",
  rejected: "Rejected",
};

const STATUS_TONE: Record<ImportRequest["status"], "info" | "success" | "danger"> = {
  pending: "info",
  approved: "success",
  rejected: "danger",
};

function RejectModal(props: {
  request: ImportRequest;
  busy: boolean;
  onCancel: () => void;
  onReject: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  return (
    <FormModal
      open
      onOpenChange={(o) => !o && props.onCancel()}
      title={`Reject ${props.request.filename ?? "import"}`}
      description="The file is discarded and the requester is told why. This cannot be undone."
      onSubmit={(e) => {
        e.preventDefault();
        props.onReject(reason.trim());
      }}
      busy={props.busy}
      submitLabel="Reject import"
    >
      <Field label="Reason" hint="Optional, but it helps the requester fix and resubmit.">
        <Textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          placeholder="e.g. Wrong warehouse codes — please use the depot codes."
        />
      </Field>
    </FormModal>
  );
}
