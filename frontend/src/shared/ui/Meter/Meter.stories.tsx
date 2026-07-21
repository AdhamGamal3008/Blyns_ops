import type { Meta, StoryObj } from "@storybook/react-vite";
import { Meter } from "./Meter";

const meta = {
  title: "Data/Meter",
  component: Meter,
  args: { value: 42, label: "CPU utilisation" },
} satisfies Meta<typeof Meter>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div style={{ width: 280 }}>
      <Meter value={42} label="CPU utilisation" />
    </div>
  ),
};

/** Tone is a secondary encoding — the number beside the bar always carries the
 *  state, so a colourblind reader loses nothing. */
export const Thresholds: Story = {
  render: () => (
    <div style={{ display: "grid", gap: 20, width: 280 }}>
      {[42, 80, 96].map((pct) => (
        <div key={pct} style={{ display: "grid", gap: 6 }}>
          <span style={{ fontFamily: "var(--font-ui)", fontSize: "var(--step--1)" }}>
            Disk <b>{pct}%</b>
          </span>
          <Meter value={pct} label={`Disk utilisation ${pct}%`} />
        </div>
      ))}
    </div>
  ),
};

export const Seats: Story = {
  render: () => (
    <div style={{ display: "grid", gap: 6, width: 200 }}>
      <span style={{ fontFamily: "var(--font-ui)", fontSize: "var(--step--1)" }}>
        Seats <b>18 / 25</b>
      </span>
      <Meter value={18} max={25} label="Seats used at Acme Co." />
    </div>
  ),
};
