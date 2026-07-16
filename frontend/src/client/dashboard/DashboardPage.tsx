// The tenant landing surface (docs/modules/CLIENT_DASHBOARD.md): Quick System
// Actions, KPIs, Calendar View, System Activity Panel.

import { useOutletContext } from "react-router-dom";
import type { ClientMe } from "../../shared/types";
import { ActivityPanel } from "./ActivityPanel";
import { CalendarView } from "./CalendarView";
import { KpiCards } from "./KpiCards";
import { QuickActions } from "./QuickActions";

export function DashboardPage() {
  const me = useOutletContext<ClientMe>();
  const canCalendar = (me.role.permissions["calendar"] ?? 0) >= 2;
  const canActivity = (me.role.permissions["activity"] ?? 0) >= 2;

  return (
    <>
      <QuickActions />
      <KpiCards />
      <div className="dash-split">
        {canCalendar ? <CalendarView /> : <div />}
        {canActivity && <ActivityPanel me={me} />}
      </div>
    </>
  );
}
