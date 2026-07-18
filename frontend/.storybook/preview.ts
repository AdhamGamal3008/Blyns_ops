import type { Preview } from "@storybook/react-vite";

// Only the token layer + fonts — deliberately NOT the legacy styles.css, so
// stories render the true design-system values (oxblood/champagne/paper/ink)
// with no legacy-role shadowing.
import "../src/shared/design/tokens.css";
import "../src/shared/design/fonts.css";

const preview: Preview = {
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
