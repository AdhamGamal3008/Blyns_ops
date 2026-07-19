import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { Switch } from "./Switch";

const meta = {
  title: "Primitives/Switch",
  component: Switch,
  args: { label: "Notify approvers automatically" },
} satisfies Meta<typeof Switch>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Interactive: Story = {
  render: (args) => {
    const [on, setOn] = useState(true);
    return <Switch {...args} checked={on} onCheckedChange={setOn} />;
  },
};

export const States: Story = {
  render: () => (
    <div style={{ display: "grid", gap: "var(--sp-3)" }}>
      <Switch label="Off" checked={false} />
      <Switch label="On" checked />
      <Switch label="Disabled" disabled />
    </div>
  ),
};
