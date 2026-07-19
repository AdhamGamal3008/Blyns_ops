import type { Meta, StoryObj } from "@storybook/react-vite";
import { Radio, RadioGroup } from "./Radio";

const meta = {
  title: "Primitives/Radio",
  component: RadioGroup,
} satisfies Meta<typeof RadioGroup>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <RadioGroup defaultValue="net30">
      <Radio value="due" label="Due on receipt" />
      <Radio value="net15" label="Net 15" />
      <Radio value="net30" label="Net 30" />
      <Radio value="net60" label="Net 60" disabled />
    </RadioGroup>
  ),
};
