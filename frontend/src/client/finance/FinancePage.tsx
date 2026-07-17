// Finance module UI (docs/modules/FINANCE.md). Posting is one-way: a draft can
// be edited, a posted document can only be voided — the UI mirrors that.

import { useState } from "react";
import { useLocation, useOutletContext } from "react-router-dom";
import type { ClientMe } from "../../shared/types";
import { ChartSection } from "./ChartSection";
import { BillsSection } from "./BillsSection";
import { InvoicesSection } from "./InvoicesSection";
import { ReportsSection } from "./ReportsSection";

const SECTIONS = [
  { key: "invoices", label: "Invoices" },
  { key: "bills", label: "Bills" },
  { key: "reports", label: "Reports" },
  { key: "chart", label: "Chart of accounts" },
] as const;

export function FinancePage() {
  const me = useOutletContext<ClientMe>();
  const location = useLocation();
  // the dashboard's `finance.invoice.new` quick action deep-links here
  const newInvoice = location.pathname.endsWith("/invoices/new");
  const [section, setSection] = useState<string>("invoices");
  const canWrite = (me.role.permissions["finance"] ?? 0) >= 3;

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
      {section === "invoices" && (
        <InvoicesSection canWrite={canWrite} openNew={newInvoice} />
      )}
      {section === "bills" && <BillsSection canWrite={canWrite} />}
      {section === "reports" && <ReportsSection />}
      {section === "chart" && <ChartSection canWrite={canWrite} />}
    </>
  );
}
