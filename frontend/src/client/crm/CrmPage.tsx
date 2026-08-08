// CRM module UI (docs/modules/CRM.md). Sections map to the spec's entities;
// the pipeline board is the §3 `/crm/pipeline` view.

import { useLocation, useOutletContext } from "react-router-dom";
import { csvGrants } from "../../shared/csv/access";
import { ImportApprovals } from "../../shared/csv/ImportApprovals";
import { PageHeader } from "../../shared/shell";
import type { ClientMe } from "../../shared/types";
import { Stack, Tabs, TabsContent, TabsList, TabsTrigger } from "../../shared/ui";
import { AccountsSection } from "./AccountsSection";
import { ContactsSection } from "./ContactsSection";
import { CrmAnalytics } from "./CrmAnalytics";
import { LeadsSection } from "./LeadsSection";
import { PipelineBoard } from "./PipelineBoard";

export function CrmPage() {
  const me = useOutletContext<ClientMe>();
  const { pathname } = useLocation();
  const canWrite = (me.role.permissions["crm"] ?? 0) >= 3;
  const canAnalytics = (me.role.permissions["crm_analytics"] ?? 0) >= 1;
  const csv = (entity: string) => csvGrants(me, "crm", entity);

  // Dashboard quick actions deep-link to /app/crm/<section>[/new]: pick the tab
  // from the path (a bare /app/crm lands on the pipeline) and open the section's
  // create modal when the path ends in /new. Deals live on the pipeline board.
  const tab = pathname.startsWith("/app/crm/leads") ? "leads"
    : pathname.startsWith("/app/crm/contacts") ? "contacts"
    : pathname.startsWith("/app/crm/accounts") ? "accounts"
    : "pipeline";
  const isNew = pathname.endsWith("/new");

  return (
    <Stack>
      <PageHeader title="CRM" description="Leads, deals, accounts, and the people behind them" />

      <ImportApprovals me={me} module="crm" />

      <Tabs defaultValue={tab}>
        <TabsList>
          <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
          <TabsTrigger value="leads">Leads</TabsTrigger>
          <TabsTrigger value="accounts">Accounts</TabsTrigger>
          <TabsTrigger value="contacts">Contacts</TabsTrigger>
          {canAnalytics && <TabsTrigger value="analytics">Analytics</TabsTrigger>}
        </TabsList>

        <TabsContent value="pipeline">
          <PipelineBoard canWrite={canWrite} csv={csv("deals")}
            openNew={pathname.startsWith("/app/crm/deals") && isNew} />
        </TabsContent>
        <TabsContent value="leads">
          <LeadsSection canWrite={canWrite} csv={csv("leads")}
            openNew={tab === "leads" && isNew} />
        </TabsContent>
        <TabsContent value="accounts">
          <AccountsSection canWrite={canWrite} csv={csv("accounts")} />
        </TabsContent>
        <TabsContent value="contacts">
          <ContactsSection canWrite={canWrite} csv={csv("contacts")}
            openNew={tab === "contacts" && isNew} />
        </TabsContent>
        {canAnalytics && (
          <TabsContent value="analytics">
            <CrmAnalytics />
          </TabsContent>
        )}
      </Tabs>
    </Stack>
  );
}
