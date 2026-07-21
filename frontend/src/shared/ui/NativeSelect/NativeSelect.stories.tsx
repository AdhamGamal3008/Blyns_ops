import type { Meta, StoryObj } from "@storybook/react-vite";
import { Field } from "../Field/Field";
import { NativeSelect } from "./NativeSelect";

const stages = ["new", "qualified", "proposal", "negotiation", "won", "lost"].map((s) => ({
  value: s,
  label: s,
}));

const meta = {
  title: "Primitives/NativeSelect",
  component: NativeSelect,
  args: { options: stages, defaultValue: "proposal" },
} satisfies Meta<typeof NativeSelect>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div style={{ width: 280 }}>
      <Field label="Stage">
        <NativeSelect options={stages} defaultValue="proposal" />
      </Field>
    </div>
  ),
};

/** The compact size is why this exists: dense repeating rows — a kanban card,
 *  a table cell — where a portalled listbox would be too heavy. */
export const Compact: Story = {
  render: () => (
    <div style={{ width: 180 }}>
      <NativeSelect selectSize="compact" options={stages} defaultValue="new"
        aria-label="Move deal to another stage" />
    </div>
  ),
};

export const Invalid: Story = {
  render: () => (
    <div style={{ width: 280 }}>
      <Field label="Stage" error="Pick a stage before saving.">
        <NativeSelect options={stages} invalid />
      </Field>
    </div>
  ),
};
