import type { Meta, StoryObj } from "@storybook/react-vite";
import { PackageOpen, Plus } from "lucide-react";
import { Button } from "../Button/Button";
import { EmptyState } from "./EmptyState";

const meta = {
  title: "Primitives/EmptyState",
  component: EmptyState,
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    icon: <PackageOpen />,
    title: "No products yet",
    description: "Add your first SKU to start tracking stock levels and movements.",
    action: (
      <Button iconLeft={<Plus />}>Add product</Button>
    ),
  },
};
