import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button } from "../Button/Button";
import { Field } from "../Field/Field";
import { Input } from "../Input/Input";
import { Select } from "../Select/Select";
import { Switch } from "../Switch/Switch";
import { Textarea } from "../Textarea/Textarea";
import { FormActions, FormGrid, FormSection } from "./Form";

const meta = {
  title: "Data/Form",
  component: FormSection,
  args: { children: null },
} satisfies Meta<typeof FormSection>;

export default meta;
type Story = StoryObj<typeof meta>;

export const GroupedWithStickyActions: Story = {
  render: () => (
    <div style={{ maxWidth: 640, maxHeight: 460, overflowY: "auto", padding: "var(--sp-5)", border: "1px solid var(--border)", borderRadius: "var(--r-lg)", background: "var(--surface-raised)" }}>
      <FormSection title="Company" description="Shown to employees across their portal.">
        <FormGrid>
          <Field label="Company name" required>
            <Input defaultValue="Oakwood Interiors" />
          </Field>
          <Field label="Slug" hint="Used in the workspace URL.">
            <Input defaultValue="oakwood" />
          </Field>
        </FormGrid>
        <Field label="Description">
          <Textarea placeholder="What does this company do?" />
        </Field>
      </FormSection>

      <FormSection title="Defaults" description="Applied to new projects and invoices.">
        <FormGrid>
          <Field label="Service line">
            <Select
              options={[
                { value: "cladding", label: "Wall cladding" },
                { value: "flooring", label: "Flooring" },
                { value: "furniture", label: "Custom furniture" },
              ]}
              defaultValue="cladding"
            />
          </Field>
          <Field label="Payment terms">
            <Select
              options={[
                { value: "net15", label: "Net 15" },
                { value: "net30", label: "Net 30" },
              ]}
              defaultValue="net30"
            />
          </Field>
        </FormGrid>
        <Switch label="Notify approvers automatically" defaultChecked />
      </FormSection>

      <FormActions sticky>
        <Button variant="ghost">Cancel</Button>
        <Button>Save changes</Button>
      </FormActions>
    </div>
  ),
};
