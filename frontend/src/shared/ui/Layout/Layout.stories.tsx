import type { Meta, StoryObj } from "@storybook/react-vite";
import { Badge } from "../Badge/Badge";
import { Card } from "../Card/Card";
import { KpiCard } from "../KpiCard/KpiCard";
import { Grid, Row, Split, Stack } from "./Layout";

const meta = {
  title: "Data/Layout",
  component: Stack,
  args: { children: null },
} satisfies Meta<typeof Stack>;

export default meta;
type Story = StoryObj<typeof meta>;

const Block = ({ children }: { children: React.ReactNode }) => (
  <Card>{children}</Card>
);

export const StackStory: Story = {
  name: "Stack",
  render: () => (
    <Stack gap={4}>
      <Block>First</Block>
      <Block>Second</Block>
      <Block>Third</Block>
    </Stack>
  ),
};

/** Auto-fitting: columns drop as the container narrows, no breakpoints. */
export const GridStory: Story = {
  name: "Grid",
  render: () => (
    <Grid min={200}>
      <KpiCard label="Open projects" value="12" />
      <KpiCard label="Open deals" value="7" />
      <KpiCard label="Low stock" value="3" />
      <KpiCard label="Unpaid" value="$8,863" />
    </Grid>
  ),
};

/** Main column + companion rail; collapses to one column under 1024px. */
export const SplitStory: Story = {
  name: "Split",
  render: () => (
    <Split asideWidth={280}>
      <Block>Main column — a table, a calendar, a board.</Block>
      <Block>Aside — activity, filters, summary.</Block>
    </Split>
  ),
};

export const RowStory: Story = {
  name: "Row",
  render: () => (
    <Row>
      <Badge tone="success">active</Badge>
      <Badge tone="warning">low stock</Badge>
      <Badge tone="danger">overdue</Badge>
      <Badge tone="neutral">archived</Badge>
    </Row>
  ),
};
