// The six client-portal module views the Platform section showcases, built from
// the REAL design-system components with realistic mock data — so they look
// exactly like the shipped product without any backend, login, or screenshot
// capture. Rendered live (and scaled) by ScreenFrame; never captured to a file.

import { CircleCheck, FolderKanban, Package, Receipt, SlidersHorizontal, TriangleAlert, Wallet } from "lucide-react";
import type { CSSProperties, ReactElement } from "react";
import { PageHeader } from "../../shared/shell";
import {
  Badge,
  type BadgeTone,
  Banner,
  BarChart,
  Button,
  Card,
  CardHeader,
  DataTable,
  type DataTableColumn,
  KpiCard,
  type RailStage,
  StageRail,
  type StageState,
  TrendChart,
} from "../../shared/ui";
import { MockShell } from "./MockShell";

const kpiGrid: CSSProperties = {
  display: "grid",
  gap: "var(--sp-4)",
  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  marginBottom: "var(--sp-5)",
};
const twoCol: CSSProperties = { display: "grid", gap: "var(--sp-4)", gridTemplateColumns: "1fr 1fr" };
const cardGrid: CSSProperties = {
  display: "grid",
  gap: "var(--sp-4)",
  gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))",
};

// --- mock data -------------------------------------------------------------

const revenue = [
  { month: "Jan", revenue: 82000, costs: 61000 },
  { month: "Feb", revenue: 91000, costs: 64000 },
  { month: "Mar", revenue: 78000, costs: 59000 },
  { month: "Apr", revenue: 104000, costs: 71000 },
  { month: "May", revenue: 118000, costs: 74000 },
  { month: "Jun", revenue: 132000, costs: 80000 },
];
const byStage = [
  { stage: "Design", count: 6 },
  { stage: "Procure", count: 4 },
  { stage: "Production", count: 9 },
  { stage: "Install", count: 3 },
  { stage: "Handover", count: 2 },
];
const egp = (v: number) => `EGP ${(v / 1000).toFixed(0)}k`;

const jobs = [
  ["Oakwood Residence", "Stage 7 · Site Readiness", "Awaiting approval"],
  ["Marina Bay Offices", "Stage 5 · Procurement", "On track"],
  ["Cedar Hill Villas", "Stage 3 · Design Package", "In review"],
  ["Atlas Retail Group", "Stage 8 · Installation", "On site"],
  ["Novena Clinic", "Stage 6 · Factory Release", "On track"],
  ["Harbour Point Lofts", "Stage 2 · Site Survey", "Scheduled"],
];

const STAGE_NAMES: [string, string, string | null][] = [
  ["project_initiation", "Initiation", "project_director"],
  ["site_survey", "Site Survey", null],
  ["design_package", "Design Package", "design_manager"],
  ["measurement_verification", "Design Freeze", "engineering"],
  ["material_procurement", "Procurement", "procurement_manager"],
  ["factory_release", "Factory Release", "production_manager"],
  ["site_readiness", "Site Readiness", "project_manager"],
  ["installation", "Installation", "project_manager"],
  ["final_inspection_handover", "Handover", "project_director"],
];
function stages(current: number): RailStage[] {
  return STAGE_NAMES.map(([key, name, role], i): RailStage => {
    const order = i + 1;
    const status: StageState =
      order < current ? "approved" : order === current ? "pending_approval" : "pending";
    return { order, key, name, status, approverRole: role };
  });
}

interface Lead {
  id: string;
  company: string;
  contact: string;
  stage: "New" | "Qualified" | "Proposal" | "Won";
  owner: string;
  value: number;
}
const leadTone: Record<Lead["stage"], BadgeTone> = {
  New: "neutral", Qualified: "info", Proposal: "warning", Won: "success",
};
const leads: Lead[] = [
  { id: "1", company: "Marina Bay Offices", contact: "L. Haddad", stage: "Proposal", owner: "Sara", value: 480000 },
  { id: "2", company: "Cedar Hill Villas", contact: "N. Osman", stage: "Qualified", owner: "Karim", value: 310000 },
  { id: "3", company: "Atlas Retail Group", contact: "R. Fahmy", stage: "Won", owner: "Sara", value: 920000 },
  { id: "4", company: "Novena Clinic", contact: "M. Adel", stage: "New", owner: "Dina", value: 165000 },
  { id: "5", company: "Harbour Point Lofts", contact: "T. Nasser", stage: "Proposal", owner: "Karim", value: 540000 },
  { id: "6", company: "Skyline Fit-Out Co.", contact: "H. Aziz", stage: "Qualified", owner: "Dina", value: 275000 },
];
const leadColumns: DataTableColumn<Lead>[] = [
  { key: "company", header: "Account", sortable: true },
  { key: "contact", header: "Contact" },
  {
    key: "stage", header: "Stage", sortable: true, sortValue: (r) => r.stage,
    accessor: (r) => <Badge tone={leadTone[r.stage]}>{r.stage}</Badge>,
  },
  { key: "owner", header: "Owner" },
  {
    key: "value", header: "Est. value", numeric: true, sortable: true, sortValue: (r) => r.value,
    accessor: (r) => `EGP ${r.value.toLocaleString()}`,
  },
];

interface Item {
  id: string;
  sku: string;
  name: string;
  onHand: number;
  reserved: number;
  status: "In stock" | "Low" | "On order";
}
const itemTone: Record<Item["status"], BadgeTone> = { "In stock": "success", Low: "warning", "On order": "info" };
const items: Item[] = [
  { id: "1", sku: "OAK-VNR-18", name: "Oak veneer 18mm", onHand: 42, reserved: 30, status: "In stock" },
  { id: "2", sku: "WAL-CLD-04", name: "Walnut cladding panel", onHand: 6, reserved: 6, status: "Low" },
  { id: "3", sku: "BRS-HDL-11", name: "Brushed brass handle", onHand: 210, reserved: 64, status: "In stock" },
  { id: "4", sku: "GLS-TMP-08", name: "Tempered glass 8mm", onHand: 0, reserved: 12, status: "On order" },
  { id: "5", sku: "STL-FRM-22", name: "Steel frame section", onHand: 18, reserved: 15, status: "Low" },
  { id: "6", sku: "LAM-MTT-30", name: "Matte laminate sheet", onHand: 95, reserved: 20, status: "In stock" },
];
const itemColumns: DataTableColumn<Item>[] = [
  { key: "sku", header: "SKU", sortable: true },
  { key: "name", header: "Item", sortable: true },
  { key: "onHand", header: "On hand", numeric: true, sortable: true, sortValue: (r) => r.onHand },
  { key: "reserved", header: "Reserved", numeric: true, sortable: true, sortValue: (r) => r.reserved },
  {
    key: "status", header: "Status", sortable: true, sortValue: (r) => r.status,
    accessor: (r) => <Badge tone={itemTone[r.status]}>{r.status}</Badge>,
  },
];

interface Invoice {
  id: string;
  number: string;
  client: string;
  status: "Paid" | "Overdue" | "Draft";
  issued: string;
  amount: number;
}
const invTone: Record<Invoice["status"], BadgeTone> = { Paid: "success", Overdue: "danger", Draft: "neutral" };
const invoices: Invoice[] = [
  { id: "1", number: "INV-1042", client: "Oakwood Residence", status: "Overdue", issued: "2026-06-02", amount: 128400 },
  { id: "2", number: "INV-1041", client: "Marina Bay Offices", status: "Paid", issued: "2026-06-01", amount: 94200 },
  { id: "3", number: "INV-1040", client: "Cedar Hill Villas", status: "Paid", issued: "2026-05-28", amount: 61800 },
  { id: "4", number: "INV-1039", client: "Atlas Retail Group", status: "Draft", issued: "2026-05-26", amount: 210500 },
  { id: "5", number: "INV-1038", client: "Novena Clinic", status: "Paid", issued: "2026-05-24", amount: 44300 },
  { id: "6", number: "INV-1037", client: "Harbour Point Lofts", status: "Overdue", issued: "2026-05-20", amount: 156900 },
];
const invColumns: DataTableColumn<Invoice>[] = [
  { key: "number", header: "Invoice", sortable: true },
  { key: "client", header: "Client", sortable: true },
  {
    key: "status", header: "Status", sortable: true, sortValue: (r) => r.status,
    accessor: (r) => <Badge tone={invTone[r.status]}>{r.status}</Badge>,
  },
  { key: "issued", header: "Issued", sortable: true },
  {
    key: "amount", header: "Amount", numeric: true, sortable: true, sortValue: (r) => r.amount,
    accessor: (r) => `EGP ${r.amount.toLocaleString()}`,
  },
];

const opsTasks = [
  "Approve veneer batch — Oakwood Residence",
  "Release factory order — Novena Clinic",
  "Confirm site access — Atlas Retail Group",
  "Review procurement quote — Marina Bay Offices",
];

// --- screens ---------------------------------------------------------------

const leadership: ReactElement = (
  <MockShell active="leadership">
    <PageHeader title="Dashboard" description="Where every project, cost, and approval comes together." />
    <div style={kpiGrid}>
      <KpiCard label="Open projects" value="24" delta={{ value: "+3 this month", direction: "up" }} icon={<FolderKanban size={18} />} />
      <KpiCard label="Unpaid invoices" value="EGP 412,900" delta={{ value: "-8%", direction: "down", invertColor: true }} icon={<Receipt size={18} />} />
      <KpiCard label="Cash on hand" value="EGP 1.24M" delta={{ value: "+2.1%", direction: "up" }} icon={<Wallet size={18} />} />
      <KpiCard label="Low-stock items" value="7" delta={{ value: "+2", direction: "up", invertColor: true }} icon={<TriangleAlert size={18} />} hint="below reorder point" />
    </div>
    <div style={twoCol}>
      <Card>
        <CardHeader title="Revenue vs. costs" description="Last 6 months" />
        <TrendChart data={revenue} xKey="month" series={[{ key: "revenue", label: "Revenue" }, { key: "costs", label: "Costs" }]} formatValue={egp} />
      </Card>
      <Card>
        <CardHeader title="Projects by stage" description="Active pipeline" />
        <BarChart data={byStage} xKey="stage" series={[{ key: "count", label: "Projects" }]} />
      </Card>
    </div>
  </MockShell>
);

const projects: ReactElement = (
  <MockShell active="projects">
    <PageHeader title="Oakwood Residence" description="Stage 7 of 9 · Site Readiness Inspection" actions={<Button>Advance stage</Button>} />
    <Card>
      <CardHeader title="Stage-gate pipeline" description="Champagne marks the gate awaiting approval." />
      <StageRail stages={stages(7)} currentOrder={7} />
    </Card>
    <div style={{ ...cardGrid, marginTop: "var(--sp-4)" }}>
      {jobs.map(([name, stage, note]) => (
        <Card key={name}>
          <CardHeader title={name} description={stage} />
          <p style={{ margin: 0, color: "var(--text-muted)" }}>{note}</p>
        </Card>
      ))}
    </div>
  </MockShell>
);

const clients: ReactElement = (
  <MockShell active="clients">
    <PageHeader title="Accounts & leads" description="Every relationship, quotation and hand-off in one place." actions={<Button>New lead</Button>} />
    <DataTable data={leads} columns={leadColumns} getRowId={(r) => r.id} />
  </MockShell>
);

const inventory: ReactElement = (
  <MockShell active="inventory">
    <PageHeader title="Stock on hand" description="What's available, reserved, ordered or arriving." actions={<Button>Receive stock</Button>} />
    <div style={{ marginBottom: "var(--sp-4)" }}>
      <Banner tone="warning" title="2 SKUs below reorder point">Walnut cladding panel and steel frame section need reordering.</Banner>
    </div>
    <DataTable data={items} columns={itemColumns} getRowId={(r) => r.id} />
  </MockShell>
);

const finance: ReactElement = (
  <MockShell active="finance">
    <PageHeader title="Invoices" description="Budgets, invoices, costs and profitability — connected to the work." actions={<Button>New invoice</Button>} />
    <div style={kpiGrid}>
      <KpiCard label="Billed this month" value="EGP 1.02M" delta={{ value: "+12%", direction: "up" }} icon={<Receipt size={18} />} />
      <KpiCard label="Outstanding" value="EGP 412,900" delta={{ value: "2 overdue", direction: "down", invertColor: true }} icon={<TriangleAlert size={18} />} />
      <KpiCard label="Cash on hand" value="EGP 1.24M" delta={{ value: "+2.1%", direction: "up" }} icon={<Wallet size={18} />} />
    </div>
    <DataTable data={invoices} columns={invColumns} getRowId={(r) => r.id} />
  </MockShell>
);

const operations: ReactElement = (
  <MockShell active="operations">
    <PageHeader title="Today" description="Daily work simplified through the workflows built around your teams." />
    <div style={kpiGrid}>
      <KpiCard label="Approvals pending" value="5" delta={{ value: "2 overdue", direction: "up", invertColor: true }} icon={<SlidersHorizontal size={18} />} />
      <KpiCard label="Tasks due today" value="11" icon={<CircleCheck size={18} />} />
      <KpiCard label="On site" value="3 crews" icon={<Package size={18} />} />
    </div>
    <div style={twoCol}>
      <Card>
        <CardHeader title="Needs your approval" description="Gate reviews waiting on you" />
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-3)" }}>
          {opsTasks.map((t) => (
            <li key={t} style={{ display: "flex", gap: "var(--sp-3)", alignItems: "center" }}>
              <CircleCheck size={16} style={{ color: "var(--gold-700)", flex: "none" }} />
              <span>{t}</span>
            </li>
          ))}
        </ul>
      </Card>
      <Card>
        <CardHeader title="Projects by stage" description="Active pipeline" />
        <BarChart data={byStage} xKey="stage" series={[{ key: "count", label: "Projects" }]} />
      </Card>
    </div>
  </MockShell>
);

export const SCREENS: Record<string, ReactElement> = {
  leadership,
  projects,
  clients,
  inventory,
  finance,
  operations,
};
