import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { Field } from "../Field/Field";
import { Combobox } from "./Combobox";

const accounts = [
  { value: "oakwood", label: "Oakwood Residence" },
  { value: "marina", label: "Marina Bay Offices" },
  { value: "cedar", label: "Cedar Hill Villas" },
  { value: "atlas", label: "Atlas Retail Group" },
  { value: "novena", label: "Novena Clinic Fit-out" },
];

const meta = {
  title: "Primitives/Combobox",
  component: Combobox,
  args: { options: accounts },
} satisfies Meta<typeof Combobox>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Interactive: Story = {
  render: () => {
    const [value, setValue] = useState<string>();
    return (
      <div style={{ width: 300 }}>
        <Field label="Account">
          <Combobox
            options={accounts}
            value={value}
            onValueChange={setValue}
            placeholder="Link an account"
            searchPlaceholder="Search accounts…"
          />
        </Field>
      </div>
    );
  },
};
