import type { Meta, StoryObj } from "@storybook/react-vite";
import { ArrowRight, Plus, Trash2 } from "lucide-react";
import { Button } from "./Button";

const meta = {
  title: "Primitives/Button",
  component: Button,
  args: { children: "Onboard company" },
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Primary: Story = { args: { variant: "primary" } };
export const Secondary: Story = { args: { variant: "secondary", children: "Save draft" } };
export const Ghost: Story = { args: { variant: "ghost", children: "Cancel" } };
export const Danger: Story = {
  args: { variant: "danger", children: "Delete company", iconLeft: <Trash2 /> },
};
export const WithIcons: Story = {
  args: { children: "Continue", iconRight: <ArrowRight /> },
};
export const Loading: Story = { args: { loading: true, children: "Onboarding…" } };
export const Disabled: Story = { args: { disabled: true } };
export const Compact: Story = { args: { size: "compact", children: "Add", iconLeft: <Plus /> } };

const wrap = { display: "flex", gap: "var(--sp-3)", flexWrap: "wrap" as const, alignItems: "center" };

export const AllVariants: Story = {
  render: () => (
    <div style={{ display: "grid", gap: "var(--sp-4)" }}>
      <div style={wrap}>
        <Button variant="primary">Primary</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="danger">Danger</Button>
      </div>
      <div style={wrap}>
        <Button variant="primary" loading>
          Loading
        </Button>
        <Button variant="primary" disabled>
          Disabled
        </Button>
        <Button variant="primary" iconLeft={<Plus />}>
          With icon
        </Button>
        <Button variant="primary" size="compact">
          Compact
        </Button>
      </div>
    </div>
  ),
};
