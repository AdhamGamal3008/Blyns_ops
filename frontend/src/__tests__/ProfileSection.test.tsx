// Company profile logo lives in the Settings → Company profile form: the current
// logo previews, and the Save button persists it with the rest of the profile.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProfileSection } from "../client/settings/ProfileSection";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const PROFILE = {
  data: {
    name: "Acme", currency: "USD", timezone: "UTC", fiscal_year_start: "01-01",
    logo_ref: "data:image/png;base64,LOGO",
  },
};

function stubFetch() {
  const mock = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "PATCH") {
      return okJson({ data: { ...PROFILE.data, ...JSON.parse(String(init.body)) } });
    }
    return okJson(PROFILE);
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

describe("ProfileSection logo", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("previews the current logo and saves it via the Save button", async () => {
    const mock = stubFetch();
    render(<ProfileSection canWrite />);

    await waitFor(() =>
      expect(screen.getByAltText("Company logo").getAttribute("src"))
        .toBe("data:image/png;base64,LOGO"));

    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => {
      const patch = mock.mock.calls.find(
        ([, init]) => (init as RequestInit)?.method === "PATCH",
      );
      expect(patch).toBeTruthy();
      expect(JSON.parse(String((patch![1] as RequestInit).body)).logo_ref)
        .toBe("data:image/png;base64,LOGO");
    });
  });

  it("hides the upload input for a read-only user", async () => {
    stubFetch();
    render(<ProfileSection canWrite={false} />);
    await waitFor(() => expect(screen.getByAltText("Company logo")).toBeInTheDocument());
    expect(screen.queryByLabelText("Upload company logo")).not.toBeInTheDocument();
  });
});
