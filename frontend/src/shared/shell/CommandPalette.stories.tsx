import type { Meta, StoryObj } from "@storybook/react-vite";
import { Contact, FolderKanban, LayoutDashboard, LogOut, Package, Receipt, Settings } from "lucide-react";
import { useState } from "react";
import { Button } from "../ui/Button/Button";
import { CommandPalette } from "./CommandPalette";
import type { CommandItem } from "./types";

const commands: CommandItem[] = [
  { id: "dash", label: "Dashboard", group: "Navigate", icon: <LayoutDashboard size={18} />, onSelect: () => {} },
  { id: "proj", label: "Projects", group: "Navigate", icon: <FolderKanban size={18} />, onSelect: () => {} },
  { id: "crm", label: "CRM", group: "Navigate", icon: <Contact size={18} />, onSelect: () => {} },
  { id: "inv", label: "Inventory", group: "Navigate", icon: <Package size={18} />, onSelect: () => {} },
  { id: "fin", label: "Finance", group: "Navigate", icon: <Receipt size={18} />, onSelect: () => {} },
  { id: "set", label: "Settings", group: "Navigate", icon: <Settings size={18} />, onSelect: () => {} },
  { id: "out", label: "Sign out", group: "Account", icon: <LogOut size={18} />, onSelect: () => {} },
];

const meta = {
  title: "Shell/CommandPalette",
  component: CommandPalette,
  parameters: { layout: "fullscreen", fullBleed: true },
  args: { open: false, onOpenChange: () => {}, commands },
} satisfies Meta<typeof CommandPalette>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => {
    const [open, setOpen] = useState(true);
    return (
      <div style={{ padding: "var(--sp-6)", minHeight: "100vh", background: "var(--surface)" }}>
        <Button onClick={() => setOpen(true)}>Open command palette (⌘K)</Button>
        <CommandPalette open={open} onOpenChange={setOpen} commands={commands} />
      </div>
    );
  },
};
