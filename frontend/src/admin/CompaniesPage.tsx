// Companies: list, onboard (temp password shown once), block/unblock, seats.

import { Building2, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../shared/api";
import type { Company } from "../shared/types";
import { PageHeader } from "../shared/shell";
import {
  Badge,
  type BadgeTone,
  Banner,
  Button,
  Card,
  Checkbox,
  DataState,
  DataTable,
  type DataTableColumn,
  errorText,
  Field,
  FormModal,
  Grid,
  Input,
  Meter,
  Modal,
  Row,
  Stack,
  Stepper,
} from "../shared/ui";
import styles from "./CompaniesPage.module.css";

const ALL_MODULES = ["dashboard", "settings", "projects", "crm", "inventory", "finance"];

const STATUS_TONE: Record<string, BadgeTone> = {
  active: "success", blocked: "danger", suspended: "neutral",
  provisioning: "warning", failed: "danger",
};

interface OnboardResult {
  company: Company;
  provisioning_job_id: string;
  owner_temp_password: string | null;
}

export function CompaniesPage() {
  const [companies, setCompanies] = useState<Company[] | null>(null);
  const [showOnboard, setShowOnboard] = useState(false);
  const [seating, setSeating] = useState<Company | null>(null);
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

  const columns: DataTableColumn<Company>[] = [
    { key: "name", header: "Name", sortable: true, accessor: (c) => <b>{c.name}</b> },
    { key: "slug", header: "Slug", sortable: true },
    {
      key: "status",
      header: "Status",
      sortable: true,
      accessor: (c) => <Badge tone={STATUS_TONE[c.status] ?? "neutral"}>{c.status}</Badge>,
      sortValue: (c) => c.status,
    },
    {
      key: "seats",
      header: "Seats",
      numeric: true,
      sortable: true,
      sortValue: (c) => (c.seat_limit ? (c.seats_used ?? 0) / c.seat_limit : 0),
      accessor: (c) => (
        <div className={styles.seats}>
          <span>{c.seats_used ?? 0}/{c.seat_limit ?? 0}</span>
          <Meter
            value={c.seats_used ?? 0}
            max={c.seat_limit || 1}
            label={`Seats used at ${c.name}`}
          />
        </div>
      ),
    },
    {
      key: "modules",
      header: "Modules",
      accessor: (c) => (
        <Row gap={1}>
          {(c.enabled_modules ?? []).map((m) => (
            <Badge key={m} tone="neutral">{m}</Badge>
          ))}
        </Row>
      ),
    },
    {
      key: "actions",
      header: "",
      accessor: (c) => (
        <Row gap={2} className={styles.noWrap}>
          <Button variant="ghost" size="compact" onClick={() => setSeating(c)}>Seats</Button>
          {c.status === "active" ? (
            <Button variant="danger" size="compact" onClick={() => setStatus(c, "blocked")}>
              Block
            </Button>
          ) : c.status === "blocked" ? (
            <Button variant="ghost" size="compact" onClick={() => setStatus(c, "active")}>
              Unblock
            </Button>
          ) : null}
        </Row>
      ),
    },
  ];

  return (
    <Stack>
      <PageHeader
        title="Companies"
        description={
          companies
            ? `${companies.length} tenant${companies.length === 1 ? "" : "s"} on the platform`
            : "Tenants on the platform"
        }
        actions={
          <Button onClick={() => setShowOnboard(true)}>
            <Plus size={16} aria-hidden="true" />
            Onboard company
          </Button>
        }
      />

      {error != null && companies != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState
        loading={!companies && !error}
        error={companies ? null : error}
        onRetry={load}
        isEmpty={companies?.length === 0}
        empty={
          <Card>
            <Stack gap={3}>
              <Building2 size={24} aria-hidden="true" />
              <b>No companies yet</b>
              <span>Onboard one to provision its tenant database.</span>
            </Stack>
          </Card>
        }
      >
        <DataTable
          data={companies ?? []}
          columns={columns}
          getRowId={(c) => c.id}
          searchPlaceholder="Search companies…"
        />
      </DataState>

      {showOnboard && (
        <OnboardWizard onClose={() => { setShowOnboard(false); load(); }} />
      )}
      {seating && (
        <SeatsModal
          company={seating}
          onDone={(changed) => { setSeating(null); if (changed) load(); }}
        />
      )}
    </Stack>
  );
}

/** Seat management (ADMIN_PORTAL.md §3) — the ceiling relative to what's used. */
function SeatsModal(props: { company: Company; onDone: (changed: boolean) => void }) {
  const { company } = props;
  const used = company.seats_used ?? 0;
  const [limit, setLimit] = useState(String(company.seat_limit ?? 0));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const next = Number(limit);
  const belowUsed = next < used;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/admin/companies/${company.id}/seats`, {
        method: "PATCH", body: { seat_limit: next }, realm: "admin",
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
      title={`Seats — ${company.name}`}
      description={`${used} of ${company.seat_limit ?? 0} in use.`}
      onSubmit={submit}
      error={error}
      errorTitle="Could not update the seat limit"
      busy={busy}
      submitDisabled={belowUsed || !Number.isFinite(next) || next < 1}
      submitLabel="Update seats"
    >
      <Meter
        value={used}
        max={company.seat_limit || 1}
        label={`Seats used at ${company.name}`}
      />
      <Field label="Seat limit" required>
        <Input type="number" min={1} value={limit} required
          onChange={(e) => setLimit(e.target.value)} />
      </Field>
      {belowUsed && (
        <Banner tone="warning" title="Below the seats already in use">
          {used} employees have accounts. Block or remove employees
          before lowering the limit past that.
        </Banner>
      )}
    </FormModal>
  );
}

const STEPS = [
  { key: "company", label: "Company", description: "Name and slug" },
  { key: "owner", label: "Owner", description: "First account" },
  { key: "modules", label: "Modules", description: "What they get" },
];

/** Onboarding is provisioning a database — worth walking, not one long form. */
function OnboardWizard(props: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [seatLimit, setSeatLimit] = useState("25");
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

  const stepValid =
    step === 0
      ? name.trim() !== "" && /^[a-z0-9-]{3,40}$/.test(slug) && Number(seatLimit) >= 1
      : step === 1
        ? ownerName.trim() !== "" && /.+@.+\..+/.test(ownerEmail)
        : modules.length > 0;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (step < STEPS.length - 1) {
      setStep(step + 1);
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const res = await api<OnboardResult>("/admin/companies", {
        method: "POST", realm: "admin",
        body: {
          name, slug, seat_limit: Number(seatLimit), enabled_modules: modules,
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

  // Provisioning succeeded: the one-time password is the whole screen.
  if (result) {
    return (
      <Modal
        open
        onOpenChange={props.onClose}
        title={`${result.company.name} is ${result.company.status}`}
        description={`Tenant database ${result.company.db_name} provisioned and seeded.`}
        footer={<Button onClick={props.onClose}>Done</Button>}
      >
        <Stack gap={4}>
          <Banner tone="warning" title="Share this one-time password now">
            It is never shown again, and the owner must change it at first login.
          </Banner>
          <code className={styles.tempPw}>{result.owner_temp_password}</code>
        </Stack>
      </Modal>
    );
  }

  return (
    <FormModal
      open
      onOpenChange={(o) => !o && props.onClose()}
      size="lg"
      title="Onboard a company"
      description="Creates the tenant database, seeds it, and issues the owner's first password."
      onSubmit={submit}
      error={error}
      errorTitle="Could not onboard the company"
      busy={busy}
      submitDisabled={!stepValid}
      submitLabel={step < STEPS.length - 1 ? "Continue" : "Onboard"}
      busyLabel="Provisioning…"
    >
      <Stepper steps={STEPS} current={step} />

      {step === 0 && (
        <>
          <Field label="Company name" required>
            <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus required />
          </Field>
          <Field label="Slug" required hint="Lowercase letters, numbers, and dashes — 3 to 40 characters.">
            <Input value={slug} pattern="[a-z0-9-]{3,40}" required
              placeholder="acme"
              onChange={(e) => setSlug(e.target.value)} />
          </Field>
          <Field label="Seat limit" required>
            <Input type="number" min={1} value={seatLimit}
              onChange={(e) => setSeatLimit(e.target.value)} />
          </Field>
        </>
      )}

      {step === 1 && (
        <>
          <Field label="Owner name" required>
            <Input value={ownerName} required autoFocus
              onChange={(e) => setOwnerName(e.target.value)} />
          </Field>
          <Field label="Owner email" required>
            <Input type="email" value={ownerEmail} required
              onChange={(e) => setOwnerEmail(e.target.value)} />
          </Field>
        </>
      )}

      {step === 2 && (
        <Field label="Enabled modules" hint="A disabled module never appears in that tenant's navigation.">
          <Grid min={150} gap={2}>
            {ALL_MODULES.map((m) => (
              <Checkbox
                key={m}
                label={m}
                checked={modules.includes(m)}
                onCheckedChange={() => toggleModule(m)}
              />
            ))}
          </Grid>
        </Field>
      )}

      {step > 0 && (
        <div>
          <Button variant="ghost" onClick={() => setStep(step - 1)}>Back</Button>
        </div>
      )}
    </FormModal>
  );
}
