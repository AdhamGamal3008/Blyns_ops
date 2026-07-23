// Documents hub (docs/modules/PROJECT_MANAGEMENT.md §3.7): each project document
// shows who added it, how (uploaded file vs URL), which stage it belongs to (or
// "general"), and offers download (files) or open (URLs). Writers can add new
// documents; read-only users cannot.

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DeliverablesSection } from "../client/projects/DeliverablesSection";

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200, headers: { "Content-Type": "application/json" },
  });

const DOCS = {
  data: [
    {
      id: "d1", title: "Lobby drawing", kind: "shop_drawing",
      stage_key: "shop_drawings", current_version: 1, source_type: "upload",
      uploaded_by: "Jane Doe", uploaded_at: "2026-07-23T10:00:00Z",
      versions: [{
        v: 1, source_type: "upload", file_ref: "drawing.dwg", file_id: "f1",
        filename: "drawing.dwg", author_id: "u1", author_name: "Jane Doe",
        at: "2026-07-23T10:00:00Z", note: "initial",
      }],
      immutable_audit: [],
    },
    {
      id: "d2", title: "Design brief", kind: "report", stage_key: null,
      current_version: 1, source_type: "url", uploaded_by: "Raj K",
      uploaded_at: "2026-07-22T09:00:00Z",
      versions: [{
        v: 1, source_type: "url", file_ref: "https://x.example.com/brief.pdf",
        author_id: "u2", author_name: "Raj K", at: "2026-07-22T09:00:00Z", note: "initial",
      }],
      immutable_audit: [],
    },
  ],
};

function stubFetch() {
  const mock = vi.fn(async (url: string) => {
    const u = String(url);
    if (u.includes("/deliverables")) return okJson(DOCS);
    if (u.includes("/config/stages")) return okJson({ data: [] });
    if (u.includes("/inventory/products")) return okJson({ data: [] });
    return okJson({ data: {} });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

describe("DeliverablesSection (Documents)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("shows each document's uploader, source, and stage/general with the right action", async () => {
    stubFetch();
    render(<DeliverablesSection projectId="p1" canWrite currentStageKey="shop_drawings"
      onChanged={() => {}} />);
    await waitFor(() => expect(screen.getByText("Lobby drawing")).toBeInTheDocument());

    // uploader attribution
    expect(screen.getByText("Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("Raj K")).toBeInTheDocument();
    // source badges
    expect(screen.getByText("File")).toBeInTheDocument();
    expect(screen.getByText("URL")).toBeInTheDocument();
    // a stage-less document reads as "General"
    expect(screen.getByText("General")).toBeInTheDocument();
    // an uploaded file offers Download; a URL offers Open
    expect(screen.getByText("Download")).toBeInTheDocument();
    const open = screen.getByText("Open");
    expect(open).toHaveAttribute("href", "https://x.example.com/brief.pdf");
  });

  it("offers New document to writers but not to read-only users", async () => {
    stubFetch();
    const { rerender } = render(
      <DeliverablesSection projectId="p1" canWrite currentStageKey={null} onChanged={() => {}} />);
    await waitFor(() => expect(screen.getByText("Lobby drawing")).toBeInTheDocument());
    expect(screen.getByText("New document")).toBeInTheDocument();

    rerender(
      <DeliverablesSection projectId="p1" canWrite={false} currentStageKey={null} onChanged={() => {}} />);
    await waitFor(() =>
      expect(screen.queryByText("New document")).not.toBeInTheDocument());
  });
});
