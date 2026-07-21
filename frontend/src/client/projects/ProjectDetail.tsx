// A single project: the 16-stage pipeline as the page's spine, with the
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
import { PROJECT_TONE, humanize, money, type Project, type Timeline } from "./types";
import styles from "./ProjectDetail.module.css";

export function ProjectDetail() {
  const me = useOutletContext<ClientMe>();
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const canWrite = (me.role.permissions["projects"] ?? 0) >= 3;
  const canApprove = canWrite || Boolean(me.role.is_client_portal);

  const [project, setProject] = useState<Project | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
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
  const b = project.budget ?? { planned: 0, committed: 0, actual: 0, currency: "USD" };
  const current = timeline.current_stage_order;
  const activeOrder = selected ?? current;
  const activeStage = stages.find((s) => s.order === activeOrder);
  const pct = (n: number) => (b.planned ? `${Math.round((n / b.planned) * 100)}% of planned` : undefined);

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
            <span>
              {project.current_stage_order
                ? `Stage ${project.current_stage_order} of 16 · ${humanize(project.current_stage_key)}`
                : "No stage machine (legacy record)"}
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
          description="Select a stage to open its gates, tasks, and approval."
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
          <TabsTrigger value="deliverables">Deliverables</TabsTrigger>
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
            onChanged={reload}
          />
        </TabsContent>
        <TabsContent value="deliverables">
          <DeliverablesSection projectId={id} canWrite={canWrite} onChanged={reload} />
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
