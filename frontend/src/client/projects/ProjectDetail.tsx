// A single project: the stage-gate pipeline as the page's spine, with the
// selected stage's controls and the deliverables / reports / job-cost tabs
// beneath it (docs/modules/PROJECT_MANAGEMENT.md §12).

import { ArrowLeft, Banknote, HandCoins, Wallet } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { api } from "../../shared/api";
import { PageHeader } from "../../shared/shell";
import type { ClientMe } from "../../shared/types";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataState,
  Grid,
  KpiCard,
  type RailStage,
  Row,
  Stack,
  StageRail,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../shared/ui";
import { DeliverablesSection } from "./DeliverablesSection";
import { JobCostsSection } from "./JobCostsSection";
import { ReportsSection } from "./ReportsSection";
import { StagePanel } from "./StagePanel";
import {
  PROJECT_TONE, humanize, money,
  type ApproverEntry, type Project, type Timeline,
} from "./types";
import styles from "./ProjectDetail.module.css";
import { companyCurrency } from "../../shared/currency";

const DIRECTOR_ROLE = "project_director";

export function ProjectDetail() {
  const me = useOutletContext<ClientMe>();
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const canWrite = (me.role.permissions["projects"] ?? 0) >= 3;
  const canApprove = canWrite;

  const [project, setProject] = useState<Project | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [approvers, setApprovers] = useState<ApproverEntry[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [selected, setSelected] = useState<number | null>(null);

  const reload = useCallback(() => {
    setError(null);
    Promise.all([
      api<Project>(`/projects/${id}`),
      api<Timeline>(`/projects/${id}/timeline`),
    ])
      .then(([p, t]) => { setProject(p.data); setTimeline(t.data); })
      .catch(setError);
  }, [id]);

  useEffect(reload, [reload]);
  // who holds the project_director position — only they may waive a hard gate
  // (SOP §3; the backend enforces it too). Resolved from the approver map.
  useEffect(() => {
    api<ApproverEntry[]>("/projects/config/approver-roles")
      .then((r) => setApprovers(r.data)).catch(() => setApprovers([]));
  }, []);

  const canWaive = useMemo(() => {
    const entry = approvers.find((e) => e.approver_role === DIRECTOR_ROLE);
    if (!entry) return false;
    const roles = (entry.client_roles ?? []).map((r) => r.toLowerCase());
    return roles.includes((me.role.name ?? "").toLowerCase())
      || (entry.assigned_user_ids ?? []).includes(me.id);
  }, [approvers, me]);

  const stages = useMemo<RailStage[]>(
    () =>
      (timeline?.stages ?? []).map((s) => ({
        order: s.order,
        key: s.key,
        name: s.name,
        status: s.status,
        approverRole: s.approver_role,
        blockingReason: s.blocking_reason,
      })),
    [timeline],
  );

  if (!project || !timeline) {
    return (
      <DataState loading={!error} error={error} onRetry={reload}>
        {null}
      </DataState>
    );
  }

  // legacy/partial docs (pre-stage-machine) may lack a budget block
  const b = project.budget ?? { planned: 0, committed: 0, actual: 0, currency: companyCurrency() };
  const current = timeline.current_stage_order;
  const activeOrder = selected ?? current;
  const activeStage = stages.find((s) => s.order === activeOrder);
  const pct = (n: number) => (b.planned ? `${Math.round((n / b.planned) * 100)}% of planned` : undefined);

  // A concurrent project has no single "current" stage — several run at once, so
  // the header counts them rather than pointing at one (CONCURRENT_WORKFLOW_PLAN §Phase 3).
  const isConcurrent =
    (timeline.workflow_type ?? project.workflow_type) === "concurrent";
  const stageCount = timeline.stages.length;
  const doneCount = timeline.stages.filter((s) => s.status === "approved").length;
  const activeCount = timeline.stages.filter(
    (s) => s.status !== "approved" && s.status !== "pending",
  ).length;

  return (
    <Stack>
      <PageHeader
        title={project.name}
        description={
          <Row gap={2}>
            <span className={styles.code}>{project.code}</span>
            <Badge tone={PROJECT_TONE[project.status] ?? "neutral"}>
              {(project.status ?? "—").replace("_", " ")}
            </Badge>
            {isConcurrent && <Badge tone="info">Concurrent</Badge>}
            {/* Which configuration VERSION this project is pinned to. Two projects
                on the same configuration can be running different versions, so the
                version is part of the identity, not a footnote. */}
            {timeline.configuration_name && (
              <Badge tone="neutral">
                {timeline.configuration_name} v{timeline.config_version}
              </Badge>
            )}
            <span>
              {!project.current_stage_order
                ? "No stage machine (legacy record)"
                : isConcurrent
                  ? `${doneCount} of ${stageCount} stages complete · ${activeCount} in progress`
                  : `Stage ${project.current_stage_order} of ${stageCount} · ${humanize(project.current_stage_key)}`}
            </span>
          </Row>
        }
        actions={
          <Button variant="secondary" onClick={() => navigate("/app/projects")}>
            <ArrowLeft size={16} aria-hidden="true" />
            Projects
          </Button>
        }
      />

      <Grid min={200}>
        <KpiCard label="Planned" value={money(b.planned, b.currency)} icon={<Wallet size={18} />} />
        <KpiCard
          label="Committed"
          value={money(b.committed, b.currency)}
          icon={<HandCoins size={18} />}
          hint={pct(b.committed)}
        />
        <KpiCard
          label="Actual"
          value={money(b.actual, b.currency)}
          icon={<Banknote size={18} />}
          hint={pct(b.actual)}
        />
      </Grid>

      <Card>
        <CardHeader
          title="Stage-gate pipeline"
          description={isConcurrent
            ? "Stages 2–8 run in parallel — open any active stage to work it; Handover (9) waits for all."
            : "Select a stage to open its gates, tasks, and approval."}
          actions={
            timeline.milestones.length > 0 && (
              <Row gap={2}>
                {timeline.milestones.map((m) => (
                  <span key={m.key} className={styles.milestone}>
                    {m.name}
                    <b>{new Date(m.due_date).toLocaleDateString()}</b>
                  </span>
                ))}
              </Row>
            )
          }
        />
        <StageRail
          stages={stages}
          currentOrder={current}
          selectedKey={activeStage?.key}
          onSelect={(s) => setSelected(s.order)}
        />
      </Card>

      <Tabs defaultValue="stage">
        <TabsList>
          <TabsTrigger value="stage">Stage {activeOrder}</TabsTrigger>
          <TabsTrigger value="deliverables">Documents</TabsTrigger>
          <TabsTrigger value="reports">Reports</TabsTrigger>
          <TabsTrigger value="costs">Job costs</TabsTrigger>
        </TabsList>

        <TabsContent value="stage">
          <StagePanel
            key={activeOrder}
            projectId={id}
            order={activeOrder}
            canWrite={canWrite}
            canApprove={canApprove}
            canWaive={canWaive}
            onChanged={reload}
          />
        </TabsContent>
        <TabsContent value="deliverables">
          <DeliverablesSection
            projectId={id}
            canWrite={canWrite}
            currentStageKey={project.current_stage_key}
            onChanged={reload}
          />
        </TabsContent>
        <TabsContent value="reports">
          <ReportsSection projectId={id} canWrite={canWrite} onChanged={reload} />
        </TabsContent>
        <TabsContent value="costs">
          <JobCostsSection
            projectId={id}
            canWrite={canWrite}
            currency={b.currency}
            onChanged={reload}
          />
        </TabsContent>
      </Tabs>
    </Stack>
  );
}
