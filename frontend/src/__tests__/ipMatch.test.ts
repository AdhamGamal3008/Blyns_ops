// Lockout-guard matching (docs/IP_ACCESS_CONTROL_PLAN.md §2-F): the pure logic
// behind the add form's "this would block your current IP" warning.

import { describe, expect, it } from "vitest";
import { ipv4InCidr, ipv4ToInt, wouldBlockSelf } from "../admin/ipMatch";

describe("ipv4ToInt", () => {
  it("parses valid IPv4 addresses", () => {
    expect(ipv4ToInt("0.0.0.0")).toBe(0);
    expect(ipv4ToInt("255.255.255.255")).toBe(0xffffffff);
    expect(ipv4ToInt("192.168.1.1")).toBe(0xc0a80101);
  });

  it("rejects malformed input", () => {
    expect(ipv4ToInt("256.0.0.1")).toBeNull();
    expect(ipv4ToInt("1.2.3")).toBeNull();
    expect(ipv4ToInt("a.b.c.d")).toBeNull();
    expect(ipv4ToInt("2001:db8::1")).toBeNull();
  });
});

describe("ipv4InCidr", () => {
  it("matches addresses inside the range", () => {
    expect(ipv4InCidr("203.0.113.9", "203.0.113.0/24")).toBe(true);
    expect(ipv4InCidr("10.1.2.3", "10.0.0.0/8")).toBe(true);
    expect(ipv4InCidr("1.2.3.4", "0.0.0.0/0")).toBe(true);
    expect(ipv4InCidr("203.0.113.9", "203.0.113.9/32")).toBe(true);
  });

  it("rejects addresses outside the range and malformed CIDRs", () => {
    expect(ipv4InCidr("203.0.114.1", "203.0.113.0/24")).toBe(false);
    expect(ipv4InCidr("203.0.113.9", "203.0.113.0")).toBe(false); // no prefix
    expect(ipv4InCidr("203.0.113.9", "203.0.113.0/33")).toBe(false);
    expect(ipv4InCidr("2001:db8::1", "2001:db8::/32")).toBe(false); // IPv6 not computed
  });
});

describe("wouldBlockSelf", () => {
  const ip = "203.0.113.5";

  it("only deny rules can block", () => {
    expect(wouldBlockSelf(ip, "US", "allow", "ip", ip)).toBe(false);
  });

  it("flags an exact IP deny", () => {
    expect(wouldBlockSelf(ip, null, "deny", "ip", "203.0.113.5")).toBe(true);
    expect(wouldBlockSelf(ip, null, "deny", "ip", "203.0.113.6")).toBe(false);
  });

  it("flags a CIDR that contains the IP", () => {
    expect(wouldBlockSelf(ip, null, "deny", "cidr", "203.0.113.0/24")).toBe(true);
    expect(wouldBlockSelf(ip, null, "deny", "cidr", "198.51.100.0/24")).toBe(false);
  });

  it("flags the admin's own country (case-insensitive), only when known", () => {
    expect(wouldBlockSelf(ip, "US", "deny", "country", "us")).toBe(true);
    expect(wouldBlockSelf(ip, "US", "deny", "country", "KP")).toBe(false);
    expect(wouldBlockSelf(ip, null, "deny", "country", "US")).toBe(false);
  });

  it("never flags an empty value", () => {
    expect(wouldBlockSelf(ip, "US", "deny", "ip", "   ")).toBe(false);
  });
});
