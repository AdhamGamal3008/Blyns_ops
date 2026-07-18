// A single project: header + the 16-stage timeline and the deliverables,
// reports, and job-cost tabs (docs/modules/PROJECT_MANAGEMENT.md §12).

import { useCallback, useEffect, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { api } from "../../shared/api";
import type { ClientMe } from "../../shared/types";
import { Badge, Card, ErrorNote, Spinner } from "../../shared/ui";
import { DeliverablesSection } from "./DeliverablesSection";
import { JobCostsSection } from "./JobCostsSection";
import { ReportsSection } from "./ReportsSection";
import { TimelineSection } from "./TimelineSection";
import { PROJECT_TONE, humanize, money, type Project, type Timeline } from "./types";

const TABS = [
  { key: "timeline", label: "Timeline" },
  { key: "deliverables", label: "Deliverables" },
  { key: "reports", label: "Reports" },
  { key: "costs", label: "Job costs" },
] as const;

export function ProjectDetail() {
  const me = useOutletContext<ClientMe>();
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const canWrite = (me.role.permissions["projects"] ?? 0) >= 3;
  const canApprove = canWrite || Boolean(me.role.is_client_portal);

  const [project, setProject] = useState<Project | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tab, setTab] = useState<string>("timeline");

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

  if (error && !project) {
    return (
      <Card>
        <ErrorNote error={error} />
        <a onClick={() => navigate("/app/projects")} style={{ cursor: "pointer" }}>
          ← Back to projects
        </a>
      </Card>
    );
  }
  if (!project || !timeline) return <Spinner />;

  // legacy/partial docs (pre-stage-machine) may lack a budget block
  const b = project.budget ?? { planned: 0, committed: 0, actual: 0, currency: "USD" };

  return (
    <>
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
          <div>
            <a onClick={() => navigate("/app/projects")}
              style={{ cursor: "pointer", fontSize: 13 }}>← Projects</a>
            <h2 style={{ fontSize: 20, marginTop: 6 }}>
              {project.name}{" "}
              <span className="muted" style={{ fontWeight: 400, fontSize: 15 }}>
                {project.code}
              </span>
            </h2>
            <div style={{ marginTop: 8, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <Badge tone={PROJECT_TONE[project.status] ?? "neutral"}>
                {(project.status ?? "—").replace("_", " ")}
              </Badge>
              <span className="muted" style={{ fontSize: 13 }}>
                {project.current_stage_order
                  ? `Stage ${project.current_stage_order}/16 · ${humanize(project.current_stage_key)}`
                  : "No stage machine (legacy record)"}
              </span>
            </div>
          </div>
          <div style={{ display: "flex", gap: 18, textAlign: "right" }}>
            <Stat label="Planned" value={money(b.planned, b.currency)} />
            <Stat label="Committed" value={money(b.committed, b.currency)} />
            <Stat label="Actual" value={money(b.actual, b.currency)} />
          </div>
        </div>
      </Card>

      <div className="quick-actions">
        {TABS.map((t) => (
          <button key={t.key}
            className={`btn ${tab === t.key ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "timeline" && (
        <TimelineSection
          projectId={id} timeline={timeline}
          canWrite={canWrite} canApprove={canApprove}
          onChanged={reload}
        />
      )}
      {tab === "deliverables" && (
        <DeliverablesSection projectId={id} canWrite={canWrite} onChanged={reload} />
      )}
      {tab === "reports" && (
        <ReportsSection projectId={id} canWrite={canWrite} onChanged={reload} />
      )}
      {tab === "costs" && (
        <JobCostsSection projectId={id} canWrite={canWrite} currency={b.currency}
          onChanged={reload} />
      )}
    </>
  );
}

function Stat(props: { label: string; value: string }) {
  return (
    <div>
      <div className="kpi-label" style={{ fontSize: 11 }}>{props.label}</div>
      <div style={{ fontWeight: 700, fontSize: 15 }}>{props.value}</div>
    </div>
  );
}
