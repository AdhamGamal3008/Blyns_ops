import type { Meta, StoryObj } from "@storybook/react-vite";
import { Info } from "lucide-react";
import { Button } from "../Button/Button";
import { Tooltip } from "./Tooltip";

const meta = {
  title: "Primitives/Tooltip",
  component: Tooltip,
  args: { content: "Tooltip", children: null },
} satisfies Meta<typeof Tooltip>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div style={{ display: "flex", gap: "var(--sp-4)", alignItems: "center" }}>
      <Tooltip content="Advances the project to the next stage gate.">
        <Button>Advance stage</Button>
      </Tooltip>
      <Tooltip content="Champagne detailing is reserved for accents." side="right">
        <Button variant="ghost" aria-label="More info">
          <Info />
        </Button>
      </Tooltip>
    </div>
  ),
};
