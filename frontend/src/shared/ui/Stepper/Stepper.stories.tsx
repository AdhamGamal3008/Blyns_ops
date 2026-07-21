import type { Meta, StoryObj } from "@storybook/react-vite";
import { Stepper, type Step } from "./Stepper";

const steps: Step[] = [
  { key: "company", label: "Company", description: "Name & slug" },
  { key: "modules", label: "Modules", description: "Enable features" },
  { key: "owner", label: "Owner", description: "First admin" },
  { key: "review", label: "Review", description: "Confirm & provision" },
];

const meta = {
  title: "Data/Stepper",
  component: Stepper,
  args: { steps, current: 1 },
} satisfies Meta<typeof Stepper>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Horizontal: Story = {
  render: () => (
    <div style={{ width: 640, maxWidth: "100%" }}>
      <Stepper steps={steps} current={1} />
    </div>
  ),
};

export const Vertical: Story = {
  render: () => (
    <div style={{ width: 280 }}>
      <Stepper steps={steps} current={2} orientation="vertical" />
    </div>
  ),
};
