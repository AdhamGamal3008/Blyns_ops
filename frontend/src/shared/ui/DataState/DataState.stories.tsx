import type { Meta, StoryObj } from "@storybook/react-vite";
import { PackageOpen, Plus } from "lucide-react";
import { Button } from "../Button/Button";
import { EmptyState } from "../EmptyState/EmptyState";
import { DataState } from "./DataState";

const meta = {
  title: "Data/DataState",
  component: DataState,
  args: { children: <p style={{ margin: 0 }}>Loaded content renders here.</p> },
} satisfies Meta<typeof DataState>;

export default meta;
type Story = StoryObj<typeof meta>;

const frame = (label: string, node: React.ReactNode) => (
  <div style={{ border: "1px solid var(--border)", borderRadius: "var(--r-lg)", padding: "var(--sp-5)", background: "var(--surface-raised)" }}>
    <div style={{ fontSize: "var(--step--1)", fontWeight: 600, color: "var(--text-muted)", marginBottom: "var(--sp-3)" }}>{label}</div>
    {node}
  </div>
);

export const AllStates: Story = {
  render: () => (
    <div style={{ display: "grid", gap: "var(--sp-4)", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
      {frame("Loading", <DataState loading>x</DataState>)}
      {frame(
        "Empty",
        <DataState
          isEmpty
          empty={<EmptyState icon={<PackageOpen />} title="No products yet" description="Add your first SKU to start tracking stock." action={<Button size="compact" iconLeft={<Plus />}>Add product</Button>} />}
        >
          x
        </DataState>,
      )}
      {frame("Error", <DataState error={new Error("Finance service timed out.")} onRetry={() => {}}>x</DataState>)}
      {frame("Loaded", <DataState>Loaded content renders here.</DataState>)}
    </div>
  ),
};
