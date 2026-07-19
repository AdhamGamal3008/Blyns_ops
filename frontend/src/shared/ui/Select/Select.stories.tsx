import type { Meta, StoryObj } from "@storybook/react-vite";
import { Field } from "../Field/Field";
import { Select } from "./Select";

const options = [
  { value: "cladding", label: "Wall cladding" },
  { value: "flooring", label: "Flooring" },
  { value: "furniture", label: "Custom furniture" },
  { value: "joinery", label: "Joinery", disabled: true },
];

const meta = {
  title: "Primitives/Select",
  component: Select,
  args: { options },
} satisfies Meta<typeof Select>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div style={{ width: 280 }}>
      <Select options={options} placeholder="Choose a service line" />
    </div>
  ),
};

export const InField: Story = {
  render: () => (
    <div style={{ width: 280 }}>
      <Field label="Service line" required>
        <Select options={options} defaultValue="cladding" />
      </Field>
    </div>
  ),
};
