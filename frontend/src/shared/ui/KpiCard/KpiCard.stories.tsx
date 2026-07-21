import type { Meta, StoryObj } from "@storybook/react-vite";
import { FolderKanban, Receipt, TriangleAlert, Wallet } from "lucide-react";
import { KpiCard } from "./KpiCard";

const meta = {
  title: "Data/KpiCard",
  component: KpiCard,
  args: { label: "Open projects", value: "24" },
} satisfies Meta<typeof KpiCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Single: Story = {
  args: {
    label: "Open projects",
    value: "24",
    delta: { value: "+3 this month", direction: "up" },
    icon: <FolderKanban size={18} />,
  },
};

export const Grid: Story = {
  render: () => (
    <div
      style={{
        display: "grid",
        gap: "var(--sp-4)",
        gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
        maxWidth: 900,
      }}
    >
      <KpiCard label="Open projects" value="24" delta={{ value: "+3", direction: "up" }} icon={<FolderKanban size={18} />} />
      <KpiCard
        label="Unpaid invoices"
        value="EGP 412,900"
        delta={{ value: "-8%", direction: "down", invertColor: true }}
        icon={<Receipt size={18} />}
      />
      <KpiCard label="Cash on hand" value="EGP 1.24M" delta={{ value: "+2.1%", direction: "up" }} icon={<Wallet size={18} />} />
      <KpiCard
        label="Low-stock items"
        value="7"
        delta={{ value: "+2", direction: "up", invertColor: true }}
        icon={<TriangleAlert size={18} />}
        hint="below reorder point"
      />
    </div>
  ),
};
