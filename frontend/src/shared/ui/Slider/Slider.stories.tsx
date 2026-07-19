import type { Meta, StoryObj } from "@storybook/react-vite";
import { Slider } from "./Slider";

const meta = {
  title: "Primitives/Slider",
  component: Slider,
} satisfies Meta<typeof Slider>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Single: Story = {
  render: () => (
    <div style={{ width: 320 }}>
      <Slider defaultValue={[40]} max={100} step={1} />
    </div>
  ),
};

export const Range: Story = {
  render: () => (
    <div style={{ width: 320 }}>
      <Slider defaultValue={[25, 75]} max={100} step={1} />
    </div>
  ),
};
