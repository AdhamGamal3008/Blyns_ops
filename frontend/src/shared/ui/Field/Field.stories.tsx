import type { Meta, StoryObj } from "@storybook/react-vite";
import { Input } from "../Input/Input";
import { Select } from "../Select/Select";
import { Textarea } from "../Textarea/Textarea";
import { Field } from "./Field";

const meta = {
  title: "Primitives/Field",
  component: Field,
  args: { label: "Company name", children: <Input /> },
} satisfies Meta<typeof Field>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div style={{ width: 320 }}>
      <Field label="Company name">
        <Input defaultValue="Acme Corp" />
      </Field>
    </div>
  ),
};

export const Required: Story = {
  render: () => (
    <div style={{ width: 320 }}>
      <Field label="Slug" required hint="Lowercase letters, numbers, and dashes.">
        <Input defaultValue="acme" />
      </Field>
    </div>
  ),
};

/** The error replaces the hint and wires aria-invalid + aria-describedby onto
 *  the control automatically. */
export const WithError: Story = {
  render: () => (
    <div style={{ width: 320 }}>
      <Field label="Slug" required error="That slug is already taken.">
        <Input defaultValue="acme" />
      </Field>
    </div>
  ),
};

export const Controls: Story = {
  render: () => (
    <div style={{ display: "grid", gap: 20, width: 320 }}>
      <Field label="Currency" hint="ISO 4217.">
        <Select
          defaultValue="USD"
          options={["USD", "EUR", "GBP"].map((c) => ({ value: c, label: c }))}
        />
      </Field>
      <Field label="Scope">
        <Textarea rows={3} defaultValue="Lobby cladding, levels 1–3." />
      </Field>
    </div>
  ),
};
