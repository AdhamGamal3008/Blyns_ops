import type { Meta, StoryObj } from "@storybook/react-vite";
import { Field } from "../Field/Field";
import { Textarea } from "./Textarea";

const meta = {
  title: "Primitives/Textarea",
  component: Textarea,
  args: { placeholder: "Add a note…" },
} satisfies Meta<typeof Textarea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { render: (args) => <div style={{ width: 360 }}><Textarea {...args} /></div> };

export const InField: Story = {
  render: () => (
    <div style={{ width: 360 }}>
      <Field label="Rejection reason" hint="The client will see this message.">
        <Textarea placeholder="Explain what needs to change…" />
      </Field>
    </div>
  ),
};
