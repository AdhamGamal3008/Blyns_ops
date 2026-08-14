// Production module UI (docs/PRODUCTION_MODULE_PLAN.md). Work-centre tabs: Queue
// (default landing) + Work Orders (Phase 1), Quality (Phase 2), Stations
// (Phase 3), Dispatch — packing → staging → shipping + manifest (Phase 4), and
// a management-only Analytics tab (Phase 5).

import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../../shared/api";
import { PageHeader } from "../../shared/shell";
import type { ClientMe } from "../../shared/types";
import { Stack, Tabs, TabsContent, TabsList, TabsTrigger } from "../../shared/ui";
import { DispatchSection } from "./DispatchSection";
import { ProductionAnalytics } from "./ProductionAnalytics";
import { QualitySection } from "./QualitySection";
import { QueueSection } from "./QueueSection";
import { StationsSection } from "./StationsSection";
import { WorkOrdersSection } from "./WorkOrdersSection";

export function ProductionPage() {
  const me = useOutletContext<ClientMe>();
  const canWrite = (me.role.permissions["production"] ?? 0) >= 3;
  const canAnalytics = (me.role.permissions["production_analytics"] ?? 0) >= 1;
  const [canManage, setCanManage] = useState(false);

  useEffect(() => {
    if (!canWrite) return;
    api<{ can_manage: boolean }>("/production/context")
      .then((r) => setCanManage(r.data.can_manage))
      .catch(() => setCanManage(false));
  }, [canWrite]);

  return (
    <Stack>
      <PageHeader
        title="Production"
        description="The factory floor — work orders below the project, executing Stage 6 · Factory Release"
      />
      <Tabs defaultValue="queue">
        <TabsList>
          <TabsTrigger value="queue">Queue</TabsTrigger>
          <TabsTrigger value="work-orders">Work Orders</TabsTrigger>
          <TabsTrigger value="quality">Quality</TabsTrigger>
          <TabsTrigger value="stations">Stations</TabsTrigger>
          <TabsTrigger value="dispatch">Dispatch</TabsTrigger>
          {canAnalytics && <TabsTrigger value="analytics">Analytics</TabsTrigger>}
        </TabsList>

        <TabsContent value="queue"><QueueSection /></TabsContent>
        <TabsContent value="work-orders">
          <WorkOrdersSection canWrite={canWrite} canManage={canManage} />
        </TabsContent>
        <TabsContent value="quality">
          <QualitySection canWrite={canWrite} canManage={canManage} />
        </TabsContent>
        <TabsContent value="stations"><StationsSection /></TabsContent>
        <TabsContent value="dispatch">
          <DispatchSection canWrite={canWrite} canManage={canManage} />
        </TabsContent>
        {canAnalytics && (
          <TabsContent value="analytics"><ProductionAnalytics /></TabsContent>
        )}
      </Tabs>
    </Stack>
  );
}
