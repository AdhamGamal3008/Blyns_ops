import type { Meta, StoryObj } from "@storybook/react-vite";
import { Plus } from "lucide-react";
import { Button } from "../ui/Button/Button";
import { PageHeader } from "./PageHeader";

const meta = {
  title: "Shell/PageHeader",
  component: PageHeader,
} satisfies Meta<typeof PageHeader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    title: "Inventory",
    description: "Stock levels, movements, and low-stock alerts across every material.",
    actions: <Button iconLeft={<Plus />}>Add product</Button>,
  },
};

export const TitleOnly: Story = {
  args: { title: "Settings" },
};
