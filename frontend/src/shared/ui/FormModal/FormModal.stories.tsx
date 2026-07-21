import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { Button } from "../Button/Button";
import { Field } from "../Field/Field";
import { Input } from "../Input/Input";
import { Select } from "../Select/Select";
import { FormModal } from "./FormModal";

const meta = {
  title: "Overlays/FormModal",
  component: FormModal,
  args: { open: false, onOpenChange: () => {}, title: "Form", onSubmit: () => {}, children: null },
} satisfies Meta<typeof FormModal>;

export default meta;
type Story = StoryObj<typeof meta>;

function Demo(props: { error?: unknown; busy?: boolean; destructive?: boolean; label: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button onClick={() => setOpen(true)}>{props.label}</Button>
      <FormModal
        open={open}
        onOpenChange={setOpen}
        title="New deal"
        description="Drafts stay editable until they are sent."
        onSubmit={(e) => {
          e.preventDefault();
          setOpen(false);
        }}
        error={props.error}
        busy={props.busy}
        destructive={props.destructive}
        submitLabel={props.destructive ? "Mark lost" : "Create deal"}
      >
        <Field label="Title" required>
          <Input defaultValue="Tower A cladding" required />
        </Field>
        <Field label="Amount">
          <Input type="number" defaultValue="42000" />
        </Field>
        <Field label="Stage">
          <Select
            defaultValue="proposal"
            options={["new", "qualified", "proposal"].map((s) => ({ value: s, label: s }))}
          />
        </Field>
      </FormModal>
    </>
  );
}

export const Default: Story = { render: () => <Demo label="Open form" /> };

/** A rejected submit keeps the dialog open and puts the reason at the top. */
export const WithError: Story = {
  render: () => <Demo label="Open with error" error={new Error("A deal with that title already exists.")} />,
};

export const Busy: Story = { render: () => <Demo label="Open while saving" busy /> };

export const Destructive: Story = { render: () => <Demo label="Open destructive" destructive /> };
