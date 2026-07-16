// API client: envelope unwrap, ApiError from the error envelope, and the
// refresh-on-401 rotation flow (docs/TESTING.md §4).

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, getTokens, setTokens } from "../shared/api";

const okJson = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status, headers: { "Content-Type": "application/json" },
  });

describe("api client", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });
  afterEach(() => vi.restoreAllMocks());

  it("unwraps the {data, meta} envelope", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      okJson({ data: [{ id: "1" }], meta: { total: 1 } }),
    ));
    const res = await api<{ id: string }[]>("/things");
    expect(res.data).toEqual([{ id: "1" }]);
    expect(res.meta).toEqual({ total: 1 });
  });

  it("throws ApiError with the error-envelope code", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      okJson({ error: { code: "SEAT_LIMIT_REACHED", message: "Full.", details: {} } }, 409),
    ));
    const err = await api("/things").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("SEAT_LIMIT_REACHED");
    expect(err.status).toBe(409);
  });

  it("refreshes once on 401 and retries with rotated tokens", async () => {
    setTokens("client", { access_token: "old-a", refresh_token: "old-r" });
    const fetchMock = vi.fn()
      // 1st: original request → 401
      .mockResolvedValueOnce(okJson({ error: { code: "PERMISSION_DENIED", message: "x" } }, 401))
      // 2nd: refresh → new pair
      .mockResolvedValueOnce(okJson({ data: { access_token: "new-a", refresh_token: "new-r" } }))
      // 3rd: retried request → success
      .mockResolvedValueOnce(okJson({ data: { ok: true } }));
    vi.stubGlobal("fetch", fetchMock);

    const res = await api<{ ok: boolean }>("/things");
    expect(res.data.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(getTokens("client")).toEqual({
      access_token: "new-a", refresh_token: "new-r",
    });
    // retried call used the NEW access token
    const retryHeaders = fetchMock.mock.calls[2][1].headers as Record<string, string>;
    expect(retryHeaders.Authorization).toBe("Bearer new-a");
  });

  it("clears tokens when the refresh itself is rejected", async () => {
    setTokens("client", { access_token: "a", refresh_token: "r" });
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(okJson({ error: { code: "PERMISSION_DENIED", message: "x" } }, 401))
      .mockResolvedValueOnce(okJson({ error: { code: "PERMISSION_DENIED", message: "revoked" } }, 401)),
    );
    await expect(api("/things")).rejects.toBeInstanceOf(ApiError);
    expect(getTokens("client")).toBeNull();
  });
});
