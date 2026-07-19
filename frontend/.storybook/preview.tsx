import type { Decorator, Preview } from "@storybook/react-vite";

// Only the token layer + fonts — deliberately NOT the legacy styles.css, so
// stories render the true design-system values with no legacy-role shadowing.
import "../src/shared/design/tokens.css";
import "../src/shared/design/fonts.css";

// Every story renders on the paper canvas with the UI font, so components are
// reviewed in their real context. Full-bleed stories (parameters.fullBleed,
// e.g. the app shell) skip the padded wrapper.
const withCanvas: Decorator = (Story, context) => {
  if (context.parameters.fullBleed) return <Story />;
  return (
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
};

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
