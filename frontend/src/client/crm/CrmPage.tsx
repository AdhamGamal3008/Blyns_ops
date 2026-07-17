// CRM module UI (docs/modules/CRM.md). Sections map to the spec's entities;
// the pipeline board is the §3 `/crm/pipeline` view.

import { useState } from "react";
import { useLocation, useOutletContext } from "react-router-dom";
import type { ClientMe } from "../../shared/types";
import { AccountsSection } from "./AccountsSection";
import { ContactsSection } from "./ContactsSection";
import { LeadsSection } from "./LeadsSection";
import { PipelineBoard } from "./PipelineBoard";

const SECTIONS = [
  { key: "pipeline", label: "Pipeline" },
  { key: "leads", label: "Leads" },
  { key: "accounts", label: "Accounts" },
  { key: "contacts", label: "Contacts" },
] as const;

export function CrmPage() {
  const me = useOutletContext<ClientMe>();
  const location = useLocation();
  // the dashboard's `crm.lead.new` quick action deep-links to /app/crm/leads/new
  const deepLink = location.pathname.startsWith("/app/crm/leads");
  const [section, setSection] = useState<string>(deepLink ? "leads" : "pipeline");
  const canWrite = (me.role.permissions["crm"] ?? 0) >= 3;

  return (
    <>
      <div className="quick-actions">
        {SECTIONS.map((s) => (
          <button key={s.key}
            className={`btn ${section === s.key ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setSection(s.key)}>
            {s.label}
          </button>
        ))}
      </div>
      {section === "pipeline" && <PipelineBoard canWrite={canWrite} />}
      {section === "leads" && (
        <LeadsSection canWrite={canWrite}
          openNew={deepLink && location.pathname.endsWith("/new")} />
      )}
      {section === "accounts" && <AccountsSection canWrite={canWrite} />}
      {section === "contacts" && <ContactsSection canWrite={canWrite} />}
    </>
  );
}
