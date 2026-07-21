import type { Meta, StoryObj } from "@storybook/react-vite";
import { ErrorState } from "./ErrorState";

const meta = {
  title: "Data/ErrorState",
  component: ErrorState,
} satisfies Meta<typeof ErrorState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    title: "Couldn't load invoices",
    description: "The finance service didn't respond. This is usually temporary.",
    onRetry: () => {},
  },
};
