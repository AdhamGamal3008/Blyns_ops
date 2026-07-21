import type { Meta, StoryObj } from "@storybook/react-vite";
import { BarChart, TrendChart } from "./Chart";

const revenue = [
  { month: "Jan", revenue: 82000, costs: 61000 },
  { month: "Feb", revenue: 91000, costs: 64000 },
  { month: "Mar", revenue: 78000, costs: 59000 },
  { month: "Apr", revenue: 104000, costs: 71000 },
  { month: "May", revenue: 118000, costs: 74000 },
  { month: "Jun", revenue: 132000, costs: 80000 },
];

const byStage = [
  { stage: "Design", count: 6 },
  { stage: "Quote", count: 4 },
  { stage: "Production", count: 9 },
  { stage: "Install", count: 3 },
  { stage: "Handover", count: 2 },
];

const egp = (v: number) => `EGP ${(v / 1000).toFixed(0)}k`;

const meta = {
  title: "Data/Chart",
  component: TrendChart,
  args: { data: revenue, xKey: "month", series: [{ key: "revenue" }] },
} satisfies Meta<typeof TrendChart>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Trend: Story = {
  render: () => (
    <div style={{ width: 640, maxWidth: "100%" }}>
      <TrendChart
        data={revenue}
        xKey="month"
        series={[
          { key: "revenue", label: "Revenue" },
          { key: "costs", label: "Costs" },
        ]}
        formatValue={egp}
      />
    </div>
  ),
};

export const Bars: Story = {
  render: () => (
    <div style={{ width: 640, maxWidth: "100%" }}>
      <BarChart data={byStage} xKey="stage" series={[{ key: "count", label: "Projects" }]} />
    </div>
  ),
};
