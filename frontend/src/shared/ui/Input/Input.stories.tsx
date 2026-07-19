import type { Meta, StoryObj } from "@storybook/react-vite";
import { Search } from "lucide-react";
import { Field } from "../Field/Field";
import { Input } from "./Input";

const meta = {
  title: "Primitives/Input",
  component: Input,
  args: { placeholder: "Acme Co." },
} satisfies Meta<typeof Input>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const WithIcon: Story = { args: { iconLeft: <Search />, placeholder: "Search companies…" } };
export const Compact: Story = { args: { inputSize: "compact" } };
export const Disabled: Story = { args: { disabled: true, value: "Read-only" } };
export const Invalid: Story = { args: { invalid: true, value: "not-an-email" } };

export const InField: Story = {
  render: () => (
    <div style={{ display: "grid", gap: "var(--sp-4)", width: 320 }}>
      <Field label="Company name" required hint="Shown to employees on their portal.">
        <Input placeholder="Acme Co." />
      </Field>
      <Field label="Contact email" error="Enter a valid email address.">
        <Input defaultValue="not-an-email" />
      </Field>
    </div>
  ),
};
