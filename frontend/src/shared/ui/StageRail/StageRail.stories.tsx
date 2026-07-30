import type { Meta, StoryObj } from "@storybook/react-vite";
import { StageRail, type RailStage, type StageState } from "./StageRail";

// The real v2.0 9-stage machine from stage_definitions.json (Stage 2 has no
// approver — it auto-advances).
const NAMES: [string, string, string | null][] = [
  ["project_initiation", "Project Initiation", "project_director"],
  ["site_survey", "Site Survey & Technical Assessment", null],
  ["design_package", "Design Package", "design_manager"],
  ["measurement_verification", "Measurement Verification & Design Freeze", "engineering"],
  ["material_procurement", "Material Procurement", "procurement_manager"],
  ["factory_release", "Factory Release", "production_manager"],
  ["site_readiness", "Site Readiness Inspection", "project_manager"],
  ["installation", "Installation", "project_manager"],
  ["final_inspection_handover", "Final Inspection & Client Handover", "project_director"],
];

function build(
  current: number,
  overrides: Record<number, { status: StageState; blockingReason?: string }> = {},
): RailStage[] {
  return NAMES.map(([key, name, role], i) => {
    const order = i + 1;
    const override = overrides[order];
    const status: StageState =
      override?.status ?? (order < current ? "approved" : order === current ? "in_progress" : "pending");
    return {
      order,
      key,
      name,
      status,
      approverRole: role,
      blockingReason: override?.blockingReason,
    };
  });
}

const meta = {
  title: "Signature/StageRail",
  component: StageRail,
  args: { stages: build(7, { 7: { status: "pending_approval" } }), currentOrder: 7 },
} satisfies Meta<typeof StageRail>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The live gate: stage 7 awaiting approval — champagne marks it. */
export const AwaitingGate: Story = {};

/** Oxblood flags a rejected stage; ochre flags a blocking gate. */
export const RejectedAndBlocked: Story = {
  args: {
    currentOrder: 4,
    stages: build(4, {
      4: { status: "rejected", blockingReason: "Veneer batch failed grain match" },
      5: { status: "blocked", blockingReason: "Awaiting supplier lead time" },
    }),
  },
};

export const VerticalTimeline: Story = {
  args: {
    orientation: "vertical",
    currentOrder: 7,
    stages: build(7, { 7: { status: "pending_approval" } }),
  },
  render: (args) => (
    <div style={{ maxWidth: 340 }}>
      <StageRail {...args} />
    </div>
  ),
};
