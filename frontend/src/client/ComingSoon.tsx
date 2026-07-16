import { useParams } from "react-router-dom";

const PHASES: Record<string, string> = {
  settings: "Phase 6",
  crm: "Phase 7",
  inventory: "Phase 8",
  finance: "Phase 9",
  projects: "Phase 10",
};

export function ComingSoon() {
  const { module } = useParams();
  return (
    <div className="coming-soon">
      <h2>{module?.toUpperCase()}</h2>
      <p>This module lands in {PHASES[module ?? ""] ?? "a later phase"} of the build.</p>
    </div>
  );
}
