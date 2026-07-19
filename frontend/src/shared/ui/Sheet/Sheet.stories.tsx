import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { Button } from "../Button/Button";
import { Field } from "../Field/Field";
import { Input } from "../Input/Input";
import { Sheet } from "./Sheet";

const meta = {
  title: "Overlays/Sheet",
  component: Sheet,
  args: { open: false, onOpenChange: () => {}, title: "Sheet" },
} satisfies Meta<typeof Sheet>;

export default meta;
type Story = StoryObj<typeof meta>;

export const RightDrawer: Story = {
  render: () => {
    const [open, setOpen] = useState(false);
    return (
      <>
        <Button onClick={() => setOpen(true)}>Edit account</Button>
        <Sheet
          open={open}
          onOpenChange={setOpen}
          title="Edit account"
          description="Changes apply to the client portal immediately."
          footer={
            <>
              <Button variant="ghost" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button onClick={() => setOpen(false)}>Save changes</Button>
            </>
          }
        >
          <div style={{ display: "grid", gap: "var(--sp-4)" }}>
            <Field label="Account name">
              <Input defaultValue="Oakwood Residence" />
            </Field>
            <Field label="Primary contact">
              <Input defaultValue="lina@oakwood.example" />
            </Field>
          </div>
        </Sheet>
      </>
    );
  },
};
