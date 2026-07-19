import type { Meta, StoryObj } from "@storybook/react-vite";
import { Badge, type BadgeTone, type BadgeVariant } from "./Badge";

const meta = {
  title: "Primitives/Badge",
  component: Badge,
  args: { children: "Active", tone: "brand" },
} satisfies Meta<typeof Badge>;

export default meta;
type Story = StoryObj<typeof meta>;

const tones: BadgeTone[] = ["neutral", "brand", "success", "warning", "danger", "info"];
const variants: BadgeVariant[] = ["soft", "solid", "outline"];

export const Default: Story = {};

export const WithDot: Story = { args: { dot: true, tone: "success", children: "Paid" } };

export const Matrix: Story = {
  render: () => (
    <div style={{ display: "grid", gap: "var(--sp-4)" }}>
      {variants.map((variant) => (
        <div key={variant} style={{ display: "flex", gap: "var(--sp-2)", flexWrap: "wrap" }}>
          {tones.map((tone) => (
            <Badge key={tone} tone={tone} variant={variant}>
              {tone}
            </Badge>
          ))}
        </div>
      ))}
    </div>
  ),
};
