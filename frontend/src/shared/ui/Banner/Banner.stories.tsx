import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button } from "../Button/Button";
import { Banner } from "./Banner";

const meta = {
  title: "Primitives/Banner",
  component: Banner,
  args: {
    title: "Approval required",
    children: "Stage 6 cannot advance until the client signs off on the veneer selection.",
  },
} satisfies Meta<typeof Banner>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Info: Story = { args: { tone: "info" } };
export const Success: Story = {
  args: { tone: "success", title: "Company onboarded", children: "Acme Co. is ready to invite employees." },
};
export const Warning: Story = { args: { tone: "warning", title: "Low stock", children: "3 SKUs are below reorder point." } };
export const Danger: Story = {
  args: { tone: "danger", title: "Payment overdue", children: "Invoice #1042 is 14 days past due." },
};
export const Dismissible: Story = { args: { tone: "info", onDismiss: () => {} } };
export const WithAction: Story = {
  args: {
    tone: "warning",
    action: (
      <Button size="compact" variant="secondary">
        Review
      </Button>
    ),
  },
};
