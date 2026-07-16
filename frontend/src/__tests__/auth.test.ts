// Auth store: token persistence per realm, forced-reset revocation.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { getTokens, setTokens } from "../shared/api";
import { changePassword, clientLogin, clientLogout } from "../shared/auth";

const okJson = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  });

describe("auth store", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("clientLogin stores client-realm tokens and surfaces the reset flag", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okJson({
      data: {
        access_token: "a1", refresh_token: "r1", token_type: "bearer",
        password_reset_required: true,
        user: { id: "u1", name: "Jane", email: "jane@acme.com" },
      },
    })));
    const result = await clientLogin("acme", "jane@acme.com", "temp");
    expect(result.password_reset_required).toBe(true);
    expect(getTokens("client")).toEqual({ access_token: "a1", refresh_token: "r1" });
    expect(getTokens("admin")).toBeNull(); // realms never mix
  });

  it("changePassword clears local tokens (server revoked refresh jtis)", async () => {
    setTokens("client", { access_token: "a", refresh_token: "r" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okJson({
      data: { password_changed: true },
    })));
    await changePassword("old", "newpassword1");
    expect(getTokens("client")).toBeNull();
  });

  it("clientLogout clears tokens even if the API call fails", async () => {
    setTokens("client", { access_token: "a", refresh_token: "r" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    await clientLogout();
    expect(getTokens("client")).toBeNull();
  });
});
