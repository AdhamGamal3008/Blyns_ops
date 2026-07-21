import type { Meta, StoryObj } from "@storybook/react-vite";
import { StageRail, type RailStage, type StageState } from "./StageRail";

// The real 16-stage machine from stage_definitions.json.
const NAMES: [string, string, string][] = [
  ["lead_conversion", "Lead Conversion", "project_director"],
  ["requirements_collection", "Requirements Collection", "design_manager"],
  ["site_survey", "Site Survey", "engineering_manager"],
  ["concept_design", "Concept Design", "design_manager"],
  ["material_selection", "Material Selection", "procurement"],
  ["shop_drawings", "Shop Drawings", "engineering"],
  ["site_measurement_verification", "Site Measurement Verification", "engineering"],
  ["material_procurement", "Material Procurement", "procurement_manager"],
  ["factory_production", "Factory Production", "production_supervisor"],
  ["factory_qc", "Factory Quality Control", "qc_manager"],
  ["packing_protection", "Packing & Protection", "warehouse_manager"],
  ["delivery_planning", "Delivery Planning", "logistics"],
  ["site_readiness", "Site Readiness Inspection", "project_manager"],
  ["installation", "Installation", "site_supervisor"],
  ["final_qc", "Final Quality Inspection", "project_manager"],
  ["client_handover", "Client Handover", "project_director"],
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
    currentOrder: 9,
    stages: build(9, {
      9: { status: "rejected", blockingReason: "Veneer batch failed grain match" },
      10: { status: "blocked", blockingReason: "Awaiting QC re-inspection" },
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
