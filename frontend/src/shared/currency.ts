// The tenant's display currency (Settings → Company profile → Currency).
//
// Every money value in the SPA is formatted in this currency. It is a per-tenant,
// per-session constant — one company, one currency, fixed for as long as the user
// is logged in — so it lives in a module rather than a React context: the
// alternative is threading a provider through five modules and every DataTable
// accessor, sparkline and KPI tile to express something that never changes while
// the app is open.
//
// Set once from `/auth/me` (see shared/auth.ts). Falls back to USD only if a
// tenant somehow has no currency configured, which the company profile prevents.

let current = "USD";

export function setCompanyCurrency(code: string | null | undefined): void {
  if (code && code.trim()) current = code.trim().toUpperCase();
}

export function companyCurrency(): string {
  return current;
}

/** Format an amount in the company's currency. Intl renders the right symbol —
 *  "EGP 1,200" for Egypt, "$1,200" for the US — so no symbol is ever hardcoded. */
export function formatMoney(
  amount: number,
  options?: Intl.NumberFormatOptions,
): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: companyCurrency(),
    maximumFractionDigits: 2,
    ...options,
  }).format(amount || 0);
}
