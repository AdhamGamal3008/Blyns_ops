// CRM module UI (docs/modules/CRM.md). Sections map to the spec's entities;
// the pipeline board is the §3 `/crm/pipeline` view.

import { useLocation, useOutletContext } from "react-router-dom";
import { PageHeader } from "../../shared/shell";
import type { ClientMe } from "../../shared/types";
import { Stack, Tabs, TabsContent, TabsList, TabsTrigger } from "../../shared/ui";
import { AccountsSection } from "./AccountsSection";
import { ContactsSection } from "./ContactsSection";
import { LeadsSection } from "./LeadsSection";
import { PipelineBoard } from "./PipelineBoard";

export function CrmPage() {
  const me = useOutletContext<ClientMe>();
  const location = useLocation();
  // the dashboard's `crm.lead.new` quick action deep-links to /app/crm/leads/new
  const deepLink = location.pathname.startsWith("/app/crm/leads");
  const canWrite = (me.role.permissions["crm"] ?? 0) >= 3;

  return (
    <Stack>
      <PageHeader title="CRM" description="Leads, deals, accounts, and the people behind them" />

      <Tabs defaultValue={deepLink ? "leads" : "pipeline"}>
        <TabsList>
          <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
          <TabsTrigger value="leads">Leads</TabsTrigger>
          <TabsTrigger value="accounts">Accounts</TabsTrigger>
          <TabsTrigger value="contacts">Contacts</TabsTrigger>
        </TabsList>

        <TabsContent value="pipeline"><PipelineBoard canWrite={canWrite} /></TabsContent>
        <TabsContent value="leads">
          <LeadsSection canWrite={canWrite}
            openNew={deepLink && location.pathname.endsWith("/new")} />
        </TabsContent>
        <TabsContent value="accounts"><AccountsSection canWrite={canWrite} /></TabsContent>
        <TabsContent value="contacts"><ContactsSection canWrite={canWrite} /></TabsContent>
      </Tabs>
    </Stack>
  );
}
