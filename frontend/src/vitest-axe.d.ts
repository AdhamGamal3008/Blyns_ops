// vitest-axe 0.1.0 augments the legacy `Vi.Assertion` namespace, which Vitest 3
// no longer uses for custom matchers — so `toHaveNoViolations` is registered at
// runtime (via expect.extend in test-setup) but invisible to the type checker.
// This augments the interface Vitest 3 actually reads.

import "vitest";
import type { AxeResults } from "axe-core";

interface AxeMatchers<R = unknown> {
  toHaveNoViolations(): R;
}

declare module "vitest" {
  interface Assertion<T = unknown> extends AxeMatchers<T> {}
  interface AsymmetricMatchersContaining extends AxeMatchers {}
}

// keep AxeResults referenced so the import is not elided
export type { AxeResults };
