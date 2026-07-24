import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button } from "../Button/Button";
import { Popover } from "./Popover";

const meta = {
  title: "Primitives/Popover",
  component: Popover,
  args: { trigger: null, children: null },
} satisfies Meta<typeof Popover>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div style={{ display: "flex", gap: "var(--sp-4)", alignItems: "center" }}>
      <Popover trigger={<Button>Deal detail</Button>} side="bottom">
        <strong>Globex rollout</strong>
        <div style={{ color: "var(--text-muted)" }}>
          $25,000 · negotiation · closes 30 Sep
        </div>
      </Popover>

      <Popover
        trigger={<Button variant="ghost">Everything on this day</Button>}
        side="bottom"
        align="start"
        size="lg"
      >
        <strong>3 scheduled items</strong>
        <ul style={{ margin: "var(--sp-2) 0 0", paddingLeft: "var(--sp-4)" }}>
          <li>Invoice INV-0007 due</li>
          <li>Marriott flooring bid closes</li>
          <li>Acclimation window ends</li>
        </ul>
      </Popover>
    </div>
  ),
};
