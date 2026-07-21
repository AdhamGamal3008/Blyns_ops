// The tenant landing surface (docs/modules/CLIENT_DASHBOARD.md): Quick System
// Actions, KPIs, Calendar View, System Activity Panel.

import { useOutletContext } from "react-router-dom";
import { PageHeader } from "../../shared/shell";
import type { ClientMe } from "../../shared/types";
import { Split, Stack } from "../../shared/ui";
import { ActivityPanel } from "./ActivityPanel";
import { CalendarView } from "./CalendarView";
import { KpiCards } from "./KpiCards";
import { QuickActions } from "./QuickActions";

/** "Good morning" reads as care, and it costs one function. */
function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export function DashboardPage() {
  const me = useOutletContext<ClientMe>();
  const canCalendar = (me.role.permissions["calendar"] ?? 0) >= 2;
  const canActivity = (me.role.permissions["activity"] ?? 0) >= 2;

  return (
    <Stack>
      <PageHeader
        title={`${greeting()}, ${me.name.split(" ")[0]}`}
        description={`${me.company.name} · ${me.role.name}`}
        actions={<QuickActions />}
      />

      <KpiCards />

      {(canCalendar || canActivity) && (
        <Split asideWidth={360}>
          {canCalendar ? <CalendarView /> : <div />}
          {canActivity ? <ActivityPanel me={me} /> : <div />}
        </Split>
      )}
    </Stack>
  );
}
