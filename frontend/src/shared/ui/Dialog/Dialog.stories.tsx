import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { Button } from "../Button/Button";
import { Modal } from "./Dialog";

const meta = {
  title: "Overlays/Dialog",
  component: Modal,
  args: { open: false, onOpenChange: () => {}, title: "Dialog" },
} satisfies Meta<typeof Modal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Confirm: Story = {
  render: () => {
    const [open, setOpen] = useState(false);
    return (
      <>
        <Button variant="danger" onClick={() => setOpen(true)}>
          Delete company
        </Button>
        <Modal
          open={open}
          onOpenChange={setOpen}
          title="Delete Acme Co.?"
          description="This permanently removes the tenant database and all 42 employee accounts."
          footer={
            <>
              <Button variant="ghost" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button variant="danger" onClick={() => setOpen(false)}>
                Delete company
              </Button>
            </>
          }
        >
          <p style={{ margin: 0, color: "var(--text-muted)" }}>
            Type the company name to confirm in the real flow. This demo just closes.
          </p>
        </Modal>
      </>
    );
  },
};
