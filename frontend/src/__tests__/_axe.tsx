// Shared helper for the a11y tests: render, run axe, return the result.
//
// axe runs under jsdom, which has no layout or paint — so these tests catch
// structural and ARIA problems (missing accessible names, invalid roles,
// orphaned labels, duplicate ids, list/table structure) but NOT colour contrast
// or focus visibility, which need real geometry. Contrast is asserted against
// the tokens in contrast.test.ts; focus visibility is verified in the browser.

import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { configureAxe } from "vitest-axe";

// The colour-contrast rule needs a canvas and computed layout that jsdom does
// not provide — it can only throw here, and contrast is already asserted exactly
// against the tokens. Turn it off so these tests check what they actually can.
const axe = configureAxe({
  rules: { "color-contrast": { enabled: false } },
});

export async function axeCheck(ui: ReactElement) {
  const { container, unmount } = render(ui);
  const results = await axe(container);
  unmount();
  return results;
}
