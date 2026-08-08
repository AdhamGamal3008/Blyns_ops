// Phase A of the analytics rollout (docs/PROJECT_ANALYTICS_PLAN.md) adds a
// dedicated `projects_analytics` client resource to the RBAC matrix, shown with a
// humanized label so the Settings editor reads "Projects Analytics", not the raw key.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  CLIENT_RESOURCES,
  resourceLabel,
  RoleMatrix,
} from "../client/settings/RoleMatrix";

describe("RoleMatrix analytics resource (Phase A)", () => {
  it("humanizes resource keys for display", () => {
    expect(resourceLabel("projects_analytics")).toBe("Projects Analytics");
    expect(resourceLabel("dashboard")).toBe("Dashboard");
  });

  it("renders a Projects Analytics row in the RBAC matrix", () => {
    expect(CLIENT_RESOURCES).toContain("projects_analytics");
    render(<RoleMatrix value={{}} onChange={() => {}} />);
    // Only the row header renders this as visible text (radios use aria-label).
    expect(screen.getByText("Projects Analytics")).toBeInTheDocument();
  });
});
