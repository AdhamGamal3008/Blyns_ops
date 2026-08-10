// Production module UI (docs/PRODUCTION_MODULE_PLAN.md). Phase 1 ships the Queue
// (default landing) and the Work Orders register + generation; Quality lands in
// Phase 2, Stations in Phase 3, and Dispatch in Phase 4.

import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { api } from "../../shared/api";
import { PageHeader } from "../../shared/shell";
import type { ClientMe } from "../../shared/types";
import { Stack, Tabs, TabsContent, TabsList, TabsTrigger } from "../../shared/ui";
import { QueueSection } from "./QueueSection";
import { WorkOrdersSection } from "./WorkOrdersSection";

export function ProductionPage() {
  const me = useOutletContext<ClientMe>();
  const canWrite = (me.role.permissions["production"] ?? 0) >= 3;
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
        </TabsList>

        <TabsContent value="queue"><QueueSection /></TabsContent>
        <TabsContent value="work-orders"><WorkOrdersSection canManage={canManage} /></TabsContent>
        <TabsContent value="quality">
          <Placeholder note="The defect log, rework, and QC-hold register. A hold blocks only its own work order, never the project. Lands in Phase 2." />
        </TabsContent>
        <TabsContent value="stations">
          <Placeholder note="Load and capacity by work centre, with allocation override. Lands in Phase 3." />
        </TabsContent>
        <TabsContent value="dispatch">
          <Placeholder note="Packed → staged → shipped, with delivery note and manifest generation. Lands in Phase 4." />
        </TabsContent>
      </Tabs>
    </Stack>
  );
}

function Placeholder({ note }: { note: string }) {
  return <p style={{ color: "var(--text-muted)", maxWidth: "60ch" }}>{note}</p>;
}
