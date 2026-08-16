// Settings module UI (docs/modules/SETTINGS.md): the client-side control
// panel. Sections map 1:1 to the spec's §1.1–1.6 + the approver map.

import { useOutletContext } from "react-router-dom";
import { PageHeader } from "../../shared/shell";
import type { ClientMe } from "../../shared/types";
import { Stack, Tabs, TabsContent, TabsList, TabsTrigger } from "../../shared/ui";
import { ApproversSection } from "./ApproversSection";
import { ConfigurationsSection } from "./ConfigurationsSection";
import { EmployeesSection } from "./EmployeesSection";
import { EventsSection } from "./EventsSection";
import { InfoSection } from "./InfoSection";
import { ProfileSection } from "./ProfileSection";
import { RolesSection } from "./RolesSection";

const SECTIONS = [
  { key: "profile", label: "Company profile" },
  { key: "employees", label: "Employees" },
  { key: "roles", label: "Roles" },
  { key: "events", label: "Calendar events" },
  { key: "approvers", label: "Approvers" },
  { key: "configurations", label: "Project configurations" },
  { key: "info", label: "Security & modules" },
] as const;

export function SettingsPage() {
  const me = useOutletContext<ClientMe>();
  const canWrite = (me.role.permissions["settings"] ?? 0) >= 3;

  return (
    <Stack>
      <PageHeader
        title="Settings"
        description={`Control panel for ${me.company.name}`}
      />

      <Tabs defaultValue="profile">
        <TabsList>
          {SECTIONS.map((s) => (
            <TabsTrigger key={s.key} value={s.key}>{s.label}</TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="profile"><ProfileSection canWrite={canWrite} /></TabsContent>
        <TabsContent value="employees"><EmployeesSection canWrite={canWrite} /></TabsContent>
        <TabsContent value="roles"><RolesSection canWrite={canWrite} /></TabsContent>
        <TabsContent value="events"><EventsSection canWrite={canWrite} /></TabsContent>
        <TabsContent value="approvers"><ApproversSection canWrite={canWrite} /></TabsContent>
        <TabsContent value="configurations">
          <ConfigurationsSection canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="info"><InfoSection /></TabsContent>
      </Tabs>
    </Stack>
  );
}
