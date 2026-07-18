// Public surface of the design system foundation.
// Token CSS (tokens.css, fonts.css) is imported once in main.tsx.

export { ThemeProvider, useTheme, type Theme } from "./ThemeProvider";
export {
  palette,
  brand,
  gold,
  neutral,
  semantic,
  motion,
  readToken,
} from "./tokens";
