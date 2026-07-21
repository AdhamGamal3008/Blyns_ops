import type { Meta, StoryObj } from "@storybook/react-vite";
import { Badge, type BadgeTone } from "../Badge/Badge";
import { DataTable, type DataTableColumn, type DataTableProps } from "./DataTable";

interface Invoice {
  id: string;
  number: string;
  client: string;
  status: "paid" | "overdue" | "draft";
  issued: string;
  amount: number;
}

const statusTone: Record<Invoice["status"], BadgeTone> = {
  paid: "success",
  overdue: "danger",
  draft: "neutral",
};

const invoices: Invoice[] = [
  { id: "1", number: "INV-1042", client: "Oakwood Residence", status: "overdue", issued: "2026-06-02", amount: 128400 },
  { id: "2", number: "INV-1041", client: "Marina Bay Offices", status: "paid", issued: "2026-06-01", amount: 94200 },
  { id: "3", number: "INV-1040", client: "Cedar Hill Villas", status: "paid", issued: "2026-05-28", amount: 61800 },
  { id: "4", number: "INV-1039", client: "Atlas Retail Group", status: "draft", issued: "2026-05-26", amount: 210500 },
  { id: "5", number: "INV-1038", client: "Novena Clinic", status: "paid", issued: "2026-05-24", amount: 44300 },
  { id: "6", number: "INV-1037", client: "Harbour Point Lofts", status: "overdue", issued: "2026-05-20", amount: 156900 },
  { id: "7", number: "INV-1036", client: "Oakwood Residence", status: "paid", issued: "2026-05-18", amount: 32100 },
  { id: "8", number: "INV-1035", client: "Cedar Hill Villas", status: "draft", issued: "2026-05-15", amount: 78650 },
  { id: "9", number: "INV-1034", client: "Marina Bay Offices", status: "paid", issued: "2026-05-12", amount: 118000 },
  { id: "10", number: "INV-1033", client: "Atlas Retail Group", status: "paid", issued: "2026-05-09", amount: 55400 },
  { id: "11", number: "INV-1032", client: "Novena Clinic", status: "overdue", issued: "2026-05-05", amount: 91200 },
  { id: "12", number: "INV-1031", client: "Harbour Point Lofts", status: "paid", issued: "2026-05-02", amount: 47300 },
];

const columns: DataTableColumn<Invoice>[] = [
  { key: "number", header: "Invoice", sortable: true },
  { key: "client", header: "Client", sortable: true },
  {
    key: "status",
    header: "Status",
    sortable: true,
    sortValue: (r) => r.status,
    accessor: (r) => <Badge tone={statusTone[r.status]}>{r.status}</Badge>,
  },
  { key: "issued", header: "Issued", sortable: true },
  {
    key: "amount",
    header: "Amount",
    numeric: true,
    sortable: true,
    sortValue: (r) => r.amount,
    accessor: (r) => `EGP ${r.amount.toLocaleString()}`,
  },
];

const meta = {
  title: "Data/DataTable",
  component: DataTable,
  args: { data: invoices, columns, getRowId: (r) => r.id },
} satisfies Meta<DataTableProps<Invoice>>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Selectable: Story = { args: { selectable: true } };
