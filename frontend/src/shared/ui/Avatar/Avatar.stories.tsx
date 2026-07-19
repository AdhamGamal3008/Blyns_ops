import type { Meta, StoryObj } from "@storybook/react-vite";
import { Avatar } from "./Avatar";

const meta = {
  title: "Primitives/Avatar",
  component: Avatar,
  args: { name: "Adham Gamal" },
} satisfies Meta<typeof Avatar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Initials: Story = {
  render: () => (
    <div style={{ display: "flex", gap: "var(--sp-3)", alignItems: "center" }}>
      <Avatar name="Adham Gamal" size="sm" />
      <Avatar name="Oakwood Residence" size="md" />
      <Avatar name="Lina Farouk" size="lg" />
    </div>
  ),
};

// Self-contained data-URI image (no runtime fetch) to demonstrate the image path.
const sampleImage =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='96' height='96'>
       <defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
         <stop offset='0' stop-color='#8C1D24'/><stop offset='1' stop-color='#C9A054'/>
       </linearGradient></defs>
       <rect width='96' height='96' fill='url(#g)'/>
       <circle cx='48' cy='38' r='16' fill='#F9F8F6' opacity='0.9'/>
       <rect x='22' y='58' width='52' height='30' rx='15' fill='#F9F8F6' opacity='0.9'/>
     </svg>`,
  );

export const WithImage: Story = {
  args: { size: "lg", src: sampleImage },
};
