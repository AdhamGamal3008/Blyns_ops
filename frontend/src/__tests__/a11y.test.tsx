// Automated accessibility checks over the kit's primitives and the signature
// surfaces. axe runs in jsdom, so these assert structure and ARIA — accessible
// names, roles, relationships, list/table semantics, duplicate ids — not colour
// contrast (contrast.test.ts) or focus visibility (verified in the browser).
//
// See _axe.tsx for the harness.

import { describe, expect, it } from "vitest";
import { Badge } from "../shared/ui/Badge/Badge";
import { Banner } from "../shared/ui/Banner/Banner";
import { Button } from "../shared/ui/Button/Button";
import { Checkbox } from "../shared/ui/Checkbox/Checkbox";
import { Field } from "../shared/ui/Field/Field";
import { FormModal } from "../shared/ui/FormModal/FormModal";
import { Input } from "../shared/ui/Input/Input";
import { Meter } from "../shared/ui/Meter/Meter";
import { type RailStage, StageRail } from "../shared/ui/StageRail/StageRail";
import { RoleMatrix } from "../client/settings/RoleMatrix";
import { axeCheck } from "./_axe";

describe("a11y — primitives", () => {
  it("Button", async () => {
    expect(await axeCheck(<Button>Save</Button>)).toHaveNoViolations();
  });

  it("Badge", async () => {
    expect(await axeCheck(<Badge tone="success">active</Badge>)).toHaveNoViolations();
  });

  it("Banner", async () => {
    expect(
      await axeCheck(
        <Banner tone="danger" title="Payment overdue">
          Invoice #1042 is 14 days past due.
        </Banner>,
      ),
    ).toHaveNoViolations();
  });

  it("Checkbox has an associated label", async () => {
    expect(
      await axeCheck(<Checkbox label="Post to Finance (Dr COGS / Cr AP)" />),
    ).toHaveNoViolations();
  });

  it("Field wires its label to the control", async () => {
    expect(
      await axeCheck(
        <Field label="Company name" required>
          <Input defaultValue="Acme Corp" />
        </Field>,
      ),
    ).toHaveNoViolations();
  });

  it("Meter exposes a name and range", async () => {
    expect(
      await axeCheck(<Meter value={18} max={25} label="Seats used at Acme Co." />),
    ).toHaveNoViolations();
  });
});

const STAGES: RailStage[] = [
  { order: 1, key: "lead", name: "Lead Conversion", status: "approved" },
  { order: 2, key: "reqs", name: "Requirements Collection", status: "waiting",
    blockingReason: "Waiting on doc:architectural_drawings" },
  { order: 3, key: "survey", name: "Site Survey", status: "pending" },
];

describe("a11y — signature surfaces", () => {
  it("StageRail (interactive)", async () => {
    expect(
      await axeCheck(<StageRail stages={STAGES} currentOrder={2} onSelect={() => {}} />),
    ).toHaveNoViolations();
  });

  it("StageRail (read-only)", async () => {
    expect(
      await axeCheck(<StageRail stages={STAGES} currentOrder={2} />),
    ).toHaveNoViolations();
  });

  it("RBAC RoleMatrix", async () => {
    expect(
      await axeCheck(
        <RoleMatrix value={{ dashboard: 3, crm: 2, finance: 0 }} onChange={() => {}} />,
      ),
    ).toHaveNoViolations();
  });
});

describe("a11y — forms & dialogs", () => {
  it("FormModal (open) has a labeled dialog and wired fields", async () => {
    expect(
      await axeCheck(
        <FormModal
          open
          onOpenChange={() => {}}
          title="New account"
          description="Create a ledger account."
          onSubmit={(e) => e.preventDefault()}
        >
          <Field label="Code" required>
            <Input defaultValue="1200" />
          </Field>
          <Field label="Name" required>
            <Input defaultValue="Bank" />
          </Field>
        </FormModal>,
      ),
    ).toHaveNoViolations();
  });
});
