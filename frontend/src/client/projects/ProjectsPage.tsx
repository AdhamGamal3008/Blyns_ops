// Project Management portfolio (docs/modules/PROJECT_MANAGEMENT.md §12). The
// list is the entry point; a row opens the stage-gate detail view.

import { FolderKanban, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useOutletContext } from "react-router-dom";
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
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../shared/ui";
import { ProjectsAnalytics } from "./ProjectsAnalytics";
import {
  PROJECT_TONE,
  humanize,
  money,
  type Project,
  type ProjectConfigurationOption,
} from "./types";

export function ProjectsPage() {
  const me = useOutletContext<ClientMe>();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const canWrite = (me.role.permissions["projects"] ?? 0) >= 3;
  // The Analytics tab appears only for roles granted the separate analytics
  // resource (VIEW+); everyone else sees the portfolio exactly as before.
  const canAnalytics = (me.role.permissions["projects_analytics"] ?? 0) >= 1;
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [stageCount, setStageCount] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  // Dashboard quick actions deep-link to /app/projects/new (the same contract
  // CRM/Finance/Inventory already honour). Seed the modal from the URL so the
  // shortcut opens the create form instead of landing on an empty portfolio.
  // Guarded by canWrite: without it a read-only user could deep-link straight
  // to the create form and only discover the 403 on submit.
  const openNew = canWrite && pathname.endsWith("/new");
  const [creating, setCreating] = useState(openNew);

  const load = useCallback(() => {
    setError(null);
    api<Project[]>("/projects?page_size=100")
      .then((r) => setProjects(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);
  // the machine's length is data, not a constant — derive the "X/N" denominator
  useEffect(() => {
    api<{ order: number }[]>("/projects/config/stages")
      .then((r) => setStageCount(r.data.length)).catch(() => setStageCount(null));
  }, []);

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
        `${p.current_stage_order
          ? `${p.current_stage_order}${stageCount ? `/${stageCount}` : ""} · `
          : ""}${humanize(p.current_stage_key)}`,
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
      accessor: (p) => money(p.budget?.planned ?? 0, p.budget?.currency),
      sortValue: (p) => p.budget?.planned ?? 0,
    },
  ];

  const portfolio = (
    <Stack>
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
                ? "Create one to start the stage-gate machine."
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
    </Stack>
  );

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

      {canAnalytics ? (
        <Tabs defaultValue="portfolio">
          <TabsList>
            <TabsTrigger value="portfolio">Portfolio</TabsTrigger>
            <TabsTrigger value="analytics">Analytics</TabsTrigger>
          </TabsList>
          <TabsContent value="portfolio">{portfolio}</TabsContent>
          <TabsContent value="analytics">
            <ProjectsAnalytics />
          </TabsContent>
        </Tabs>
      ) : (
        portfolio
      )}

      <ProjectModal
        open={creating}
        onDone={(id) => {
          setCreating(false);
          // Leave /new behind either way — staying on it means the modal cannot be
          // reopened (the URL already says "new") and a refresh reopens it.
          if (id) navigate(`/app/projects/${id}`);
          else if (openNew) navigate("/app/projects", { replace: true });
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
  const [configurationId, setConfigurationId] = useState("");
  const [configurations, setConfigurations] = useState<ProjectConfigurationOption[]>([]);
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

    // Which workflows this workspace offers. Deactivated ones are excluded — they
    // stay valid for projects already running on them, but cannot start new ones.
    api<ProjectConfigurationOption[]>("/projects/config/configurations?active_only=true")
      .then((r) => {
        setConfigurations(r.data);
        const preferred = r.data.find((c) => c.is_default) ?? r.data[0];
        if (preferred) setConfigurationId(preferred.id);
      })
      // A workspace the v4 migration has not reached has no configurations; the
      // backend still accepts a create without one, so the field simply hides.
      .catch(() => setConfigurations([]));
  }, [props.open]);

  const chosen = configurations.find((c) => c.id === configurationId);

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
          // The project pins this configuration's current version for life (D1).
          // Omitted on an un-migrated workspace, where the backend falls back to
          // the legacy template.
          ...(configurationId ? { configuration_id: configurationId } : {}),
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
      description="Enters the machine at Stage 1 (Project Initiation), waiting on its onboarding documents."
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
      {configurations.length > 0 && (
        <Field
          label="Configuration"
          hint={
            chosen
              ? `${chosen.workflow_shape === "concurrent"
                  ? "Stages 2–8 run in parallel; only Handover waits for all of them."
                  : "Stages run one at a time, in order."} ${
                  chosen.description ?? ""
                } The project keeps version ${chosen.current_version} for its whole life — later edits to this configuration will not affect it.`.trim()
              : "Which set of stage documents, quality gates and thresholds this project runs on. Chosen now, not changed later."
          }
        >
          <Select
            value={configurationId}
            onValueChange={setConfigurationId}
            options={configurations.map((c) => ({
              value: c.id,
              label: c.is_default ? `${c.name} — default` : c.name,
            }))}
          />
        </Field>
      )}
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
