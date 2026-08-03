// Lockout-guard helpers for the IP rules add form (docs/IP_ACCESS_CONTROL_PLAN.md
// §2-F/§2-H): "would this new rule block my current IP?" Pure + framework-free so
// it unit-tests without rendering. Matching mirrors the backend matcher for the
// common cases; IPv6 CIDR containment is intentionally NOT computed here (a
// best-effort warning, never a hard block — the operator can still proceed).

export function ipv4ToInt(ip: string): number | null {
  const parts = ip.split(".");
  if (parts.length !== 4) return null;
  let n = 0;
  for (const part of parts) {
    if (!/^\d{1,3}$/.test(part)) return null;
    const octet = Number(part);
    if (octet > 255) return null;
    n = n * 256 + octet;
  }
  return n >>> 0;
}

/** True when an IPv4 address falls inside an IPv4 CIDR. Non-IPv4 inputs → false. */
export function ipv4InCidr(ip: string, cidr: string): boolean {
  const slash = cidr.indexOf("/");
  if (slash === -1) return false;
  const net = cidr.slice(0, slash);
  const bits = Number(cidr.slice(slash + 1));
  if (!Number.isInteger(bits) || bits < 0 || bits > 32) return false;
  const ipInt = ipv4ToInt(ip);
  const netInt = ipv4ToInt(net);
  if (ipInt === null || netInt === null) return false;
  if (bits === 0) return true;
  const mask = (0xffffffff << (32 - bits)) >>> 0;
  return (ipInt & mask) === (netInt & mask);
}

/** Would a NEW deny rule (kind/matchType/value) block the admin's current IP?
 *  Only deny rules can block. Allowlist-wins means an existing allow could still
 *  save them, so this is deliberately a cautious warning, not a verdict. */
export function wouldBlockSelf(
  myIp: string,
  myCountry: string | null,
  kind: string,
  matchType: string,
  value: string,
): boolean {
  if (kind !== "deny") return false;
  const v = value.trim();
  if (!v || !myIp) return false;
  if (matchType === "ip") return v === myIp;
  if (matchType === "cidr") return ipv4InCidr(myIp, v);
  if (matchType === "country") {
    return !!myCountry && v.toUpperCase() === myCountry.toUpperCase();
  }
  return false;
}
