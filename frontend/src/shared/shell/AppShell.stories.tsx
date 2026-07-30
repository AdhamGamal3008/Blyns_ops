import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  Contact,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  Package,
  Receipt,
  Settings,
} from "lucide-react";
import { MemoryRouter } from "react-router-dom";
import { Button } from "../ui/Button/Button";
import { Card, CardHeader } from "../ui/Card/Card";
import { AppShell } from "./AppShell";
import { PageHeader } from "./PageHeader";
import type { CommandItem, ShellNavItem } from "./types";

const nav: ShellNavItem[] = [
  { key: "dashboard", label: "Dashboard", to: "/", end: true, icon: <LayoutDashboard size={20} /> },
  { key: "projects", label: "Projects", to: "/projects", icon: <FolderKanban size={20} /> },
  { key: "crm", label: "CRM", to: "/crm", icon: <Contact size={20} /> },
  { key: "inventory", label: "Inventory", to: "/inventory", icon: <Package size={20} /> },
  { key: "finance", label: "Finance", to: "/finance", icon: <Receipt size={20} /> },
  { key: "settings", label: "Settings", to: "/settings", icon: <Settings size={20} /> },
];

const commands: CommandItem[] = [
  ...nav.map((n) => ({
    id: n.key,
    label: n.label,
    group: "Navigate",
    icon: n.icon,
    onSelect: () => {},
  })),
  { id: "signout", label: "Sign out", group: "Account", icon: <LogOut size={18} />, onSelect: () => {} },
];

function SampleContent() {
  const jobs = [
    "Oakwood Residence",
    "Marina Bay Offices",
    "Cedar Hill Villas",
    "Atlas Retail Group",
    "Novena Clinic",
    "Harbour Point Lofts",
  ];
  return (
    <>
      <PageHeader
        title="Projects"
        description="The stage-gate pipeline across every active job."
        actions={<Button>New project</Button>}
      />
      <div
        style={{
          display: "grid",
          gap: "var(--sp-4)",
          gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
        }}
      >
        {jobs.map((t) => (
          <Card key={t}>
            <CardHeader title={t} description="Stage 6 · Veneer selection" />
            <p style={{ margin: 0, color: "var(--text-muted)" }}>Awaiting client approval.</p>
          </Card>
        ))}
      </div>
    </>
  );
}

const meta = {
  title: "Shell/AppShell",
  component: AppShell,
  parameters: { layout: "fullscreen", fullBleed: true },
  args: {
    brand: { title: "Oakwood Interiors", subtitle: "Blyns workspace" },
    nav,
    user: { name: "Adham Gamal", role: "Operations lead" },
    onSignOut: () => {},
    title: "Projects",
    breadcrumbs: [{ label: "Projects" }],
    commands,
    mobileTabs: nav.slice(0, 5),
    children: <SampleContent />,
  },
} satisfies Meta<typeof AppShell>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Client: Story = {
  decorators: [
    (Story) => (
      <MemoryRouter initialEntries={["/projects"]}>
        <Story />
      </MemoryRouter>
    ),
  ],
};

export const Admin: Story = {
  decorators: [
    (Story) => (
      <MemoryRouter initialEntries={["/companies"]}>
        <Story />
      </MemoryRouter>
    ),
  ],
  args: {
    brand: { title: "Admin Portal", subtitle: "Control plane" },
    nav: [
      { key: "dashboard", label: "Platform dashboard", to: "/", end: true, icon: <LayoutDashboard size={20} /> },
      { key: "companies", label: "Companies", to: "/companies", icon: <Package size={20} /> },
    ],
    user: { name: "Platform Admin", role: "Superadmin" },
    title: "Companies",
    breadcrumbs: [{ label: "Companies" }],
    mobileTabs: undefined,
    children: (
      <>
        <PageHeader title="Companies" description="Every tenant on the platform." actions={<Button>Onboard company</Button>} />
        <Card>
          <CardHeader title="42 companies" description="38 active · 4 suspended" />
          <p style={{ margin: 0, color: "var(--text-muted)" }}>Tenant table renders here.</p>
        </Card>
      </>
    ),
  },
};
