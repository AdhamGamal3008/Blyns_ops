// Managed project status (docs/PROJECT_STATUS_PLAN.md §3.2).
//
// The menu offers exactly the transitions the backend allows — the matrix is
// mirrored here so the UI never presents a move that will 409, and `completed`
// is offered nowhere because it is reached only by approving the last stage.

import { Archive, ChevronDown, PauseCircle, PlayCircle, RotateCcw } from "lucide-react";
import { useState } from "react";
import { api } from "../../shared/api";
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Field,
  FormModal,
  Input,
} from "../../shared/ui";
import type { Project, ProjectStatus } from "./types";
import { MANUAL_TRANSITIONS } from "./types";

type Target = "active" | "on_hold" | "archived";

const ACTION: Record<Target, { verb: string; icon: typeof Archive; blurb: string }> = {
  active: {
    verb: "Resume",
    icon: PlayCircle,
    blurb: "Put the project back into active work.",
  },
  on_hold: {
    verb: "Put on hold",
    icon: PauseCircle,
    blurb: "Pause the project. It stays held until you resume it — resolving a "
      + "report will not release it.",
  },
  archived: {
    verb: "Archive",
    icon: Archive,
    blurb: "Move the project to the Archived tab. Its stage progress is kept, "
      + "and nothing can be changed until it is restored.",
  },
};

/** Leaving the archive is a restore, and re-opening a finished project is a
 *  re-open — same endpoint, different words for the human. */
function label(from: ProjectStatus, to: Target): string {
  if (from === "archived") {
    return to === "active" ? "Restore to active" : "Restore on hold";
  }
  if (from === "completed" && to === "active") return "Re-open project";
  return ACTION[to].verb;
}

export function StatusControl(props: {
  project: Project;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const { project, canWrite } = props;
  const [target, setTarget] = useState<Target | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const from = (project.status ?? "active") as ProjectStatus;
  const targets = (MANUAL_TRANSITIONS[from] ?? []) as Target[];

  if (!canWrite || targets.length === 0) return null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!target) return;
    setError(null);
    setBusy(true);
    try {
      await api(`/projects/${project.id}/status`, {
        method: "POST",
        body: { status: target, reason: reason.trim() || null },
      });
      setTarget(null);
      setReason("");
      props.onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="secondary">
            Status
            <ChevronDown size={15} aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuLabel>
            {from === "archived" ? "Restore this project" : "Change status"}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {targets.map((t) => {
            const Icon = ACTION[t].icon;
            return (
              <DropdownMenuItem key={t} onSelect={() => setTarget(t)}>
                {from === "archived" && t !== "archived"
                  ? <RotateCcw size={15} aria-hidden="true" />
                  : <Icon size={15} aria-hidden="true" />}
                {label(from, t)}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>

      {target && (
        <FormModal
          open
          onOpenChange={(o) => !o && setTarget(null)}
          title={label(from, target)}
          description={ACTION[target].blurb}
          onSubmit={submit}
          error={error}
          errorTitle="Could not change the status"
          busy={busy}
          submitLabel={label(from, target)}
        >
          <Field
            label="Reason"
            hint="Recorded on the project's status history."
          >
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={target === "on_hold"
                ? "e.g. waiting on client sign-off"
                : "optional"}
              autoFocus
            />
          </Field>
        </FormModal>
      )}
    </>
  );
}
