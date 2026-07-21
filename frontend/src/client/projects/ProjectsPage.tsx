// Project Management portfolio (docs/modules/PROJECT_MANAGEMENT.md §12). The
// list is the entry point; a row opens the 16-stage detail view.

import { FolderKanban, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import { api } from "../../shared/api";
import { PageHeader } from "../../shared/shell";
import type { ClientMe } from "../../shared/types";
import {
  Badge,
  Banner,
  Button,
  DataState,
  DataTable,
  type DataTableColumn,
  EmptyState,
  errorText,
  Field,
  FormModal,
  Input,
  Select,
  Stack,
} from "../../shared/ui";
import { PROJECT_TONE, humanize, money, type Project } from "./types";

export function ProjectsPage() {
  const me = useOutletContext<ClientMe>();
  const navigate = useNavigate();
  const canWrite = (me.role.permissions["projects"] ?? 0) >= 3;
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setError(null);
    api<Project[]>("/projects?page_size=100")
      .then((r) => setProjects(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  const columns: DataTableColumn<Project>[] = [
    {
      key: "code",
      header: "Code",
      sortable: true,
      accessor: (p) => p.code ?? "—",
    },
    {
      key: "name",
      header: "Project",
      sortable: true,
      accessor: (p) => <b>{p.name}</b>,
      sortValue: (p) => p.name,
    },
    {
      key: "stage",
      header: "Stage",
      sortable: true,
      accessor: (p) =>
        `${p.current_stage_order ? `${p.current_stage_order}/16 · ` : ""}${humanize(p.current_stage_key)}`,
      sortValue: (p) => p.current_stage_order ?? 0,
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      accessor: (p) => (
        <Badge tone={PROJECT_TONE[p.status] ?? "neutral"}>
          {(p.status ?? "—").replace("_", " ")}
        </Badge>
      ),
      sortValue: (p) => p.status ?? "",
    },
    {
      key: "budget",
      header: "Planned budget",
      numeric: true,
      sortable: true,
      accessor: (p) => money(p.budget?.planned ?? 0, p.budget?.currency ?? "USD"),
      sortValue: (p) => p.budget?.planned ?? 0,
    },
  ];

  return (
    <Stack>
      <PageHeader
        title="Projects"
        description={
          projects
            ? `${projects.length} project${projects.length === 1 ? "" : "s"} in the stage-gate pipeline`
            : "Portfolio of stage-gate projects"
        }
        actions={
          canWrite && (
            <Button onClick={() => setCreating(true)}>
              <Plus size={16} aria-hidden="true" />
              New project
            </Button>
          )
        }
      />

      {error != null && projects != null && (
        <Banner tone="danger" title="Could not refresh projects">
          {errorText(error)}
        </Banner>
      )}

      <DataState
        loading={!projects && !error}
        error={projects ? null : error}
        onRetry={load}
        isEmpty={projects?.length === 0}
        empty={
          <EmptyState
            icon={<FolderKanban size={24} />}
            title="No projects yet"
            description={
              canWrite
                ? "Create one to start the 16-stage machine."
                : "Projects appear here once a manager creates them."
            }
            action={canWrite && <Button onClick={() => setCreating(true)}>New project</Button>}
          />
        }
      >
        <DataTable
          data={projects ?? []}
          columns={columns}
          getRowId={(p) => p.id}
          searchPlaceholder="Search projects…"
          onRowClick={(p) => navigate(`/app/projects/${p.id}`)}
        />
      </DataState>

      <ProjectModal
        open={creating}
        onDone={(id) => {
          setCreating(false);
          if (id) navigate(`/app/projects/${id}`);
        }}
      />
    </Stack>
  );
}

interface AccountOption { id: string; name: string }

const NO_ACCOUNT = "__none";

function ProjectModal(props: { open: boolean; onDone: (createdId: string | null) => void }) {
  const [name, setName] = useState("");
  const [scope, setScope] = useState("");
  const [budget, setBudget] = useState("0");
  const [accountId, setAccountId] = useState(NO_ACCOUNT);
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!props.open) return;
    // linking a CRM account is optional (§1); offer it only if CRM is readable
    api<AccountOption[]>("/crm/accounts?page_size=100")
      .then((r) => setAccounts(r.data)).catch(() => setAccounts([]));
  }, [props.open]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await api<Project>("/projects", {
        method: "POST",
        body: {
          name,
          scope: scope || null,
          crm_account_id: accountId === NO_ACCOUNT ? null : accountId,
          planned_budget: Number(budget),
        },
      });
      props.onDone(r.data.id);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <FormModal
      open={props.open}
      onOpenChange={(o) => !o && props.onDone(null)}
      title="New project"
      description="Enters the machine at Stage 1 (Lead Conversion), waiting on its onboarding documents."
      onSubmit={submit}
      error={error}
      errorTitle="Could not create the project"
      busy={busy}
      submitLabel="Create project"
      busyLabel="Creating…"
    >
      <Field label="Name" required>
        <Input value={name} onChange={(e) => setName(e.target.value)} required
          placeholder="e.g. Tower A Lobby Cladding" />
      </Field>
      <Field label="Scope">
        <Input value={scope} onChange={(e) => setScope(e.target.value)}
          placeholder="Short description of the works" />
      </Field>
      <Field label="Client account (CRM)">
        <Select
          value={accountId}
          onValueChange={setAccountId}
          options={[
            { value: NO_ACCOUNT, label: "— none —" },
            ...accounts.map((a) => ({ value: a.id, label: a.name })),
          ]}
        />
      </Field>
      <Field label="Planned budget">
        <Input type="number" step="any" min="0" value={budget}
          onChange={(e) => setBudget(e.target.value)} />
      </Field>
    </FormModal>
  );
}
