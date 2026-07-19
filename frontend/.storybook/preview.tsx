import type { Decorator, Preview } from "@storybook/react-vite";

// Only the token layer + fonts — deliberately NOT the legacy styles.css, so
// stories render the true design-system values with no legacy-role shadowing.
import "../src/shared/design/tokens.css";
import "../src/shared/design/fonts.css";

// Every story renders on the paper canvas with the UI font, so components are
// reviewed in their real context.
const withCanvas: Decorator = (Story) => (
  <div
    style={{
      background: "var(--surface)",
      color: "var(--text)",
      fontFamily: "var(--font-ui)",
      fontSize: "var(--step-0)",
      lineHeight: "var(--leading-normal)",
      padding: "var(--sp-6)",
      minHeight: "100vh",
    }}
  >
    <Story />
  </div>
);

const preview: Preview = {
  decorators: [withCanvas],
  parameters: {
    layout: "fullscreen",
    backgrounds: { disable: true },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
};

export default preview;
