import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { Pagination } from "./Pagination";

const meta = {
  title: "Primitives/Pagination",
  component: Pagination,
  args: { page: 1, pageCount: 12, onPageChange: () => {} },
} satisfies Meta<typeof Pagination>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Interactive: Story = {
  render: () => {
    const [page, setPage] = useState(1);
    return <Pagination page={page} pageCount={12} onPageChange={setPage} />;
  },
};

export const MidRange: Story = {
  render: () => {
    const [page, setPage] = useState(6);
    return <Pagination page={page} pageCount={20} onPageChange={setPage} />;
  },
};

export const Few: Story = {
  render: () => {
    const [page, setPage] = useState(2);
    return <Pagination page={page} pageCount={4} onPageChange={setPage} />;
  },
};
