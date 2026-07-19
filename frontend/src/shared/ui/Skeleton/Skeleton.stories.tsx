import type { Meta, StoryObj } from "@storybook/react-vite";
import { Skeleton } from "./Skeleton";

const meta = {
  title: "Primitives/Skeleton",
  component: Skeleton,
} satisfies Meta<typeof Skeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Text: Story = { args: { variant: "text", lines: 3, width: 280 } };

export const Card: Story = {
  render: () => (
    <div style={{ display: "flex", gap: "var(--sp-3)", width: 320, alignItems: "center" }}>
      <Skeleton variant="circle" width={48} height={48} />
      <div style={{ flex: 1 }}>
        <Skeleton variant="text" width="60%" />
        <Skeleton variant="text" width="90%" />
      </div>
    </div>
  ),
};

export const Block: Story = { args: { width: 320, height: 120 } };
