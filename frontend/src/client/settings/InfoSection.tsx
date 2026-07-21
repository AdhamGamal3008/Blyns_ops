// Security policy (read-only client view, §1.5) + module visibility (§1.6).

import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Badge, Card, Spinner } from "../../shared/legacy-ui";

interface SecurityView {
  failed_login_threshold: number;
  lockout_minutes: number;
  editable: boolean;
  note: string;
}

interface ModuleView {
  module: string;
  enabled: boolean;
  self_service: boolean;
}

export function InfoSection() {
  const [security, setSecurity] = useState<SecurityView | null>(null);
  const [modules, setModules] = useState<ModuleView[] | null>(null);

  useEffect(() => {
    api<SecurityView>("/settings/security").then((r) => setSecurity(r.data)).catch(() => {});
    api<ModuleView[]>("/settings/modules").then((r) => setModules(r.data)).catch(() => {});
  }, []);

  if (!security || !modules) return <Spinner />;

  return (
    <div className="two-col">
      <Card title="Security policy (set by platform operator)">
        <table className="table">
          <tbody>
            <tr>
              <td>Failed-login threshold</td>
              <td><b>{security.failed_login_threshold}</b> attempts</td>
            </tr>
            <tr>
              <td>Lockout window</td>
              <td><b>{security.lockout_minutes}</b> minutes</td>
            </tr>
            <tr>
              <td>Client editable</td>
              <td>{security.editable ? "yes" : "no — contact the platform operator"}</td>
            </tr>
          </tbody>
        </table>
        <p className="muted">{security.note}</p>
      </Card>
      <Card title="Modules (enabled by platform operator)">
        <div className="quick-actions">
          {modules.map((m) => (
            <Badge key={m.module} tone={m.enabled ? "ok" : "neutral"}>
              {m.module}
            </Badge>
          ))}
        </div>
      </Card>
    </div>
  );
}
