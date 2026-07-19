import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button } from "../Button/Button";
import { Card, CardFooter, CardHeader } from "./Card";

const meta = {
  title: "Primitives/Card",
  component: Card,
} satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Basic: Story = {
  render: () => (
    <Card style={{ maxWidth: 420 }}>
      <CardHeader
        title="Oakwood Residence"
        description="Wall cladding · Villa 12"
        actions={<Badgeish />}
      />
      <p style={{ color: "var(--text-muted)", margin: 0 }}>
        Stage 6 of 16 — awaiting client approval on the veneer selection.
      </p>
      <CardFooter>
        <Button variant="ghost" size="compact">
          Dismiss
        </Button>
        <Button size="compact">Review</Button>
      </CardFooter>
    </Card>
  ),
};

export const Interactive: Story = {
  render: () => (
    <Card interactive style={{ maxWidth: 320 }}>
      <CardHeader title="New quote" description="Click or press Enter" />
      <p style={{ color: "var(--text-muted)", margin: 0 }}>Hover to see the elevation lift.</p>
    </Card>
  ),
};

function Badgeish() {
  return (
    <span
      style={{
        fontSize: "var(--step--1)",
        fontWeight: 600,
        color: "var(--gold-700)",
        background: "var(--gold-50)",
        padding: "var(--sp-1) var(--sp-2)",
        borderRadius: "var(--r-pill)",
      }}
    >
      In review
    </span>
  );
}
