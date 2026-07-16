// Companies: list, onboard (temp password shown once), block/unblock, seats.

import { useCallback, useEffect, useState } from "react";
import { api } from "../shared/api";
import type { Company } from "../shared/types";
import { Badge, Button, Card, ErrorNote, Field, Spinner } from "../shared/ui";

const ALL_MODULES = ["dashboard", "settings", "projects", "crm", "inventory", "finance"];

const STATUS_TONE: Record<string, string> = {
  active: "ok", blocked: "danger", suspended: "neutral",
  provisioning: "warn", failed: "danger",
};

interface OnboardResult {
  company: Company;
  provisioning_job_id: string;
  owner_temp_password: string | null;
}

export function CompaniesPage() {
  const [companies, setCompanies] = useState<Company[] | null>(null);
  const [showOnboard, setShowOnboard] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    api<Company[]>("/admin/companies?page_size=100", { realm: "admin" })
      .then((res) => setCompanies(res.data))
      .catch(setError);
  }, []);

  useEffect(load, [load]);

  async function setStatus(c: Company, status: string) {
    setError(null);
    try {
      await api(`/admin/companies/${c.id}/status`, {
        method: "PATCH", body: { status }, realm: "admin",
      });
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function editSeats(c: Company) {
    const raw = window.prompt(
      `Seat limit for ${c.name} (used: ${c.seats_used})`, String(c.seat_limit),
    );
    if (!raw) return;
    setError(null);
    try {
      await api(`/admin/companies/${c.id}/seats`, {
        method: "PATCH", body: { seat_limit: Number(raw) }, realm: "admin",
      });
      load();
    } catch (err) {
      setError(err);
    }
  }

  if (!companies) return <Spinner />;

  return (
    <>
      <Card
        title="Companies"
        actions={<Button onClick={() => setShowOnboard(true)}>Onboard company</Button>}
      >
        <ErrorNote error={error} />
        <table className="table">
          <thead>
            <tr>
              <th>Name</th><th>Slug</th><th>Status</th><th>Seats</th>
              <th>Modules</th><th></th>
            </tr>
          </thead>
          <tbody>
            {companies.map((c) => (
              <tr key={c.id}>
                <td><b>{c.name}</b></td>
                <td className="muted">{c.slug}</td>
                <td><Badge tone={STATUS_TONE[c.status]}>{c.status}</Badge></td>
                <td>{c.seats_used}/{c.seat_limit}</td>
                <td className="muted">{(c.enabled_modules ?? []).join(", ")}</td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                  <Button variant="ghost" onClick={() => editSeats(c)}>Seats</Button>{" "}
                  {c.status === "active" ? (
                    <Button variant="danger" onClick={() => setStatus(c, "blocked")}>
                      Block
                    </Button>
                  ) : c.status === "blocked" ? (
                    <Button variant="ghost" onClick={() => setStatus(c, "active")}>
                      Unblock
                    </Button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {showOnboard && (
        <OnboardModal onClose={() => { setShowOnboard(false); load(); }} />
      )}
    </>
  );
}

function OnboardModal(props: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [seatLimit, setSeatLimit] = useState(25);
  const [ownerName, setOwnerName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [modules, setModules] = useState<string[]>([...ALL_MODULES]);
  const [result, setResult] = useState<OnboardResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  function toggleModule(m: string) {
    setModules((prev) =>
      prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m],
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await api<OnboardResult>("/admin/companies", {
        method: "POST", realm: "admin",
        body: {
          name, slug, seat_limit: seatLimit, enabled_modules: modules,
          owner: { name: ownerName, email: ownerEmail },
        },
      });
      setResult(res.data);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={props.onClose}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        {!result ? (
          <>
            <h3 style={{ marginBottom: 16 }}>Onboard a company</h3>
            <ErrorNote error={error} />
            <form onSubmit={submit}>
              <Field label="Company name">
                <input value={name} onChange={(e) => setName(e.target.value)}
                  autoFocus required />
              </Field>
              <Field label="Slug (a-z, 0-9, dashes)">
                <input value={slug} pattern="[a-z0-9-]{3,40}" required
                  onChange={(e) => setSlug(e.target.value)} />
              </Field>
              <Field label="Seat limit">
                <input type="number" min={1} value={seatLimit}
                  onChange={(e) => setSeatLimit(Number(e.target.value))} />
              </Field>
              <Field label="Owner name">
                <input value={ownerName} required
                  onChange={(e) => setOwnerName(e.target.value)} />
              </Field>
              <Field label="Owner email">
                <input type="email" value={ownerEmail} required
                  onChange={(e) => setOwnerEmail(e.target.value)} />
              </Field>
              <Field label="Enabled modules">
                <div className="quick-actions">
                  {ALL_MODULES.map((m) => (
                    <label key={m} style={{ display: "flex", gap: 5, fontSize: 13 }}>
                      <input type="checkbox" style={{ width: "auto" }}
                        checked={modules.includes(m)}
                        onChange={() => toggleModule(m)} />
                      {m}
                    </label>
                  ))}
                </div>
              </Field>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <Button variant="ghost" onClick={props.onClose}>Cancel</Button>
                <Button type="submit" disabled={busy}>
                  {busy ? "Provisioning…" : "Onboard"}
                </Button>
              </div>
            </form>
          </>
        ) : (
          <>
            <h3 style={{ marginBottom: 12 }}>
              {result.company.name} is {result.company.status}
            </h3>
            <p className="muted" style={{ marginTop: 0 }}>
              Tenant database <code>{result.company.db_name}</code> provisioned
              and seeded. Share the owner&apos;s one-time password now — it is
              never shown again:
            </p>
            <div className="temp-pw">{result.owner_temp_password}</div>
            <p className="muted">
              The owner must change it at first login.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <Button onClick={props.onClose}>Done</Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
