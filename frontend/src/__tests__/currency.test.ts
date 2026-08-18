// The tenant's configured currency (Settings → Company profile) drives every
// money value in the SPA. It is latched once from /auth/me and read by each
// module's money() default, so a fix that regressed to a hardcoded "$" would show
// up here first.

import { afterEach, describe, expect, it } from "vitest";
import {
  companyCurrency,
  formatMoney,
  setCompanyCurrency,
} from "../shared/currency";
import { money as projectMoney } from "../client/projects/types";
import { money as financeMoney } from "../client/finance/types";
import { money as crmMoney } from "../client/crm/PipelineBoard";

describe("company currency", () => {
  afterEach(() => setCompanyCurrency("USD")); // don't leak state between tests

  it("defaults to USD before /me has resolved", () => {
    expect(companyCurrency()).toBe("USD");
  });

  it("latches the tenant's currency and normalises case", () => {
    setCompanyCurrency("egp");
    expect(companyCurrency()).toBe("EGP");
  });

  it("ignores empty or missing values rather than blanking the currency", () => {
    setCompanyCurrency("EGP");
    setCompanyCurrency(undefined);
    setCompanyCurrency("");
    setCompanyCurrency(null);
    expect(companyCurrency()).toBe("EGP");
  });

  it("formats amounts in the configured currency, never a hardcoded symbol", () => {
    setCompanyCurrency("EGP");
    const out = formatMoney(1200);
    // Intl may render "EGP", "E£" or "£E" depending on the ICU build — assert it
    // is NOT a dollar sign rather than pinning a locale-specific glyph.
    expect(out).not.toContain("$");
    expect(out).toMatch(/E£|E£|EGP|£/);

    setCompanyCurrency("USD");
    expect(formatMoney(1200)).toContain("$");
  });
});

describe("money helpers ignore any per-record currency", () => {
  // The exact production bug: project budgets, bills and deals store their own
  // currency (all "USD" by default), and passing it to money() overrode the
  // company currency, so amounts showed $ even with the company set to EGP.
  // This is a single-currency system: every amount is the company currency.
  afterEach(() => setCompanyCurrency("USD"));

  it.each([
    ["projects", projectMoney],
    ["finance", financeMoney],
    ["crm", crmMoney],
  ])("%s money() uses the company currency, not the record's", (_name, money) => {
    setCompanyCurrency("EGP");
    const out = money(1200, "USD"); // record says USD; must be ignored
    expect(out).not.toContain("$");
    setCompanyCurrency("USD");
    expect(money(1200, "EGP")).toContain("$"); // record says EGP; still company
  });
});
