import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button } from "../Button/Button";
import { ToastProvider, useToast } from "./Toast";

const meta = {
  title: "Overlays/Toast",
  component: ToastProvider,
  args: { children: null },
} satisfies Meta<typeof ToastProvider>;

export default meta;
type Story = StoryObj<typeof meta>;

function Demo() {
  const { toast } = useToast();
  return (
    <div style={{ display: "flex", gap: "var(--sp-3)", flexWrap: "wrap" }}>
      <Button
        onClick={() => toast({ tone: "success", title: "Company onboarded", description: "Acme Co. is ready to invite employees." })}
      >
        Onboard company
      </Button>
      <Button
        variant="secondary"
        onClick={() => toast({ tone: "info", title: "Draft saved", description: "Your changes are stored." })}
      >
        Save draft
      </Button>
      <Button
        variant="danger"
        onClick={() => toast({ tone: "danger", title: "Payment failed", description: "Card ending 6411 was declined." })}
      >
        Trigger error
      </Button>
    </div>
  );
}

export const Default: Story = {
  render: () => (
    <ToastProvider>
      <Demo />
    </ToastProvider>
  ),
};
