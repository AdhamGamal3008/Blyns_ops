import type { Meta, StoryObj } from "@storybook/react-vite";
import { Breadcrumb } from "./Breadcrumb";

const meta = {
  title: "Primitives/Breadcrumb",
  component: Breadcrumb,
} satisfies Meta<typeof Breadcrumb>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    items: [
      { label: "Projects", onClick: () => {} },
      { label: "Oakwood Residence", onClick: () => {} },
      { label: "Stage 6 — Veneer selection" },
    ],
  },
};
