import type { Meta, StoryObj } from "@storybook/react-vite";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./Tabs";

const meta = {
  title: "Primitives/Tabs",
  component: Tabs,
} satisfies Meta<typeof Tabs>;

export default meta;
type Story = StoryObj<typeof meta>;

const body = { margin: 0, color: "var(--text-muted)" };

export const Default: Story = {
  render: () => (
    <div style={{ width: 460 }}>
      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="costs">Job costs</TabsTrigger>
          <TabsTrigger value="deliverables">Deliverables</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <p style={body}>Stage 6 of 16 — awaiting client approval on the veneer selection.</p>
        </TabsContent>
        <TabsContent value="costs">
          <p style={body}>Budget consumed: 64%. Two purchase orders pending finance sign-off.</p>
        </TabsContent>
        <TabsContent value="deliverables">
          <p style={body}>3 deliverables uploaded, 1 rejected and awaiting revision.</p>
        </TabsContent>
      </Tabs>
    </div>
  ),
};
