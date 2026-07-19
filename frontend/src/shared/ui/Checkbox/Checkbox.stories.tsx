import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { Checkbox } from "./Checkbox";

const meta = {
  title: "Primitives/Checkbox",
  component: Checkbox,
  args: { label: "Email me on stage changes" },
} satisfies Meta<typeof Checkbox>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Interactive: Story = {
  render: (args) => {
    const [checked, setChecked] = useState(true);
    return <Checkbox {...args} checked={checked} onCheckedChange={(c) => setChecked(!!c)} />;
  },
};

export const States: Story = {
  render: () => (
    <div style={{ display: "grid", gap: "var(--sp-3)" }}>
      <Checkbox label="Unchecked" checked={false} />
      <Checkbox label="Checked" checked />
      <Checkbox label="Indeterminate" checked="indeterminate" />
      <Checkbox label="Disabled" disabled />
      <Checkbox label="Disabled checked" disabled checked />
    </div>
  ),
};
