// Tiny className joiner — drops falsy values. Avoids a clsx dependency.
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
