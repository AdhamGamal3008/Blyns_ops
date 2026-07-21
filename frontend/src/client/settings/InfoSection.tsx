// Security policy (read-only client view, §1.5) + module visibility (§1.6).

import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  Card,
  CardHeader,
  DataState,
  Row,
  Split,
  Stack,
} from "../../shared/ui";
import styles from "./RolesSection.module.css";

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
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api<SecurityView>("/settings/security").then((r) => setSecurity(r.data)).catch(setError);
    api<ModuleView[]>("/settings/modules").then((r) => setModules(r.data)).catch(setError);
  }, []);

  return (
    <DataState loading={(!security || !modules) && !error} error={error}>
      {security && modules && (
        <Split asideWidth={320}>
          <Card>
            <CardHeader
              title="Security policy"
              description="Set by the platform operator."
            />
            <table className={styles.overview}>
              <tbody>
                <tr>
                  <th scope="row" className={styles.roleCell}>Failed-login threshold</th>
                  <td className={styles.levelCell}><b>{security.failed_login_threshold}</b> attempts</td>
                </tr>
                <tr>
                  <th scope="row" className={styles.roleCell}>Lockout window</th>
                  <td className={styles.levelCell}><b>{security.lockout_minutes}</b> minutes</td>
                </tr>
                <tr>
                  <th scope="row" className={styles.roleCell}>Client editable</th>
                  <td className={styles.levelCell}>
                    {security.editable ? "yes" : "no — contact the platform operator"}
                  </td>
                </tr>
              </tbody>
            </table>
            <Stack gap={2}>
              <p>{security.note}</p>
            </Stack>
          </Card>

          <Card>
            <CardHeader title="Modules" description="Enabled by the platform operator." />
            <Row gap={2}>
              {modules.map((m) => (
                <Badge key={m.module} tone={m.enabled ? "success" : "neutral"}>
                  {m.module}
                </Badge>
              ))}
            </Row>
          </Card>
        </Split>
      )}
    </DataState>
  );
}
