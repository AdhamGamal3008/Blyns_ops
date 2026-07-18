// The 16-stage timeline (§4/§7). A vertical stepper of stage instances; the
// current (and any reached) stage opens the StagePanel with its gates, tasks,
// and approval actions.

import { useState } from "react";
import { Badge, Card } from "../../shared/ui";
import { StagePanel } from "./StagePanel";
import { STAGE_TONE, humanize, type Timeline } from "./types";

export function TimelineSection(props: {
  projectId: string;
  timeline: Timeline;
  canWrite: boolean;
  canApprove: boolean;
  onChanged: () => void;
}) {
  const { timeline } = props;
  const current = timeline.current_stage_order;
  const [selected, setSelected] = useState<number>(current);

  return (
    <div className="two-col">
      <Card title="Stages">
        <ol className="stepper">
          {timeline.stages.map((s) => {
            const reached = s.order <= current;
            return (
              <li key={s.order}
                className={`step ${s.order === selected ? "active" : ""} ${reached ? "" : "future"}`}
                onClick={() => reached && setSelected(s.order)}>
                <span className={`step-num badge-${STAGE_TONE[s.status]}`}>{s.order}</span>
                <span className="step-body">
                  <span className="step-name">
                    {s.name}
                    {s.order === current && (
                      <span className="muted" style={{ fontSize: 11 }}> · current</span>
                    )}
                  </span>
                  <span className="step-meta">
                    <Badge tone={STAGE_TONE[s.status]}>{s.status.replace("_", " ")}</Badge>
                    {s.approver_role && (
                      <span className="muted"> {humanize(s.approver_role)}</span>
                    )}
                    {s.recovery_loops > 0 && (
                      <span className="muted"> · ↻ {s.recovery_loops}</span>
                    )}
                  </span>
                  {s.blocking_reason && (
                    <span className="step-block">{s.blocking_reason}</span>
                  )}
                </span>
              </li>
            );
          })}
        </ol>
      </Card>

      <StagePanel
        key={selected}
        projectId={props.projectId}
        order={selected}
        canWrite={props.canWrite}
        canApprove={props.canApprove}
        onChanged={props.onChanged}
      />
    </div>
  );
}
