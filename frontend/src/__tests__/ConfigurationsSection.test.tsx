// Settings → Project configurations (docs/PROJECT_CONFIGURATIONS_PLAN.md P3).
//
// The editor is deliberately client-side only: it loads a configuration's current
// version, everything is edited in local state, and Save POSTs the whole set as a
// new version. These tests pin that contract — especially the publish payload,
// which is the entire backend surface the editor drives.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConfigurationEditor } from "../client/settings/ConfigurationEditor";
import { ConfigurationsSection } from "../client/settings/ConfigurationsSection";

const okJson = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const CONFIGS = [
  {
    id: "c1", name: "Standard", workflow_shape: "sequential",
    current_version: 1, is_system: true, is_default: true, is_active: true,
    description: "The default 9-stage pipeline.",
  },
  {
    id: "c2", name: "Concurrent", workflow_shape: "concurrent",
    current_version: 1, is_system: true, is_default: false, is_active: true,
  },
  {
    id: "c3", name: "Flooring — ASTM", workflow_shape: "sequential",
    current_version: 2, is_system: false, is_default: false, is_active: false,
  },
];

const CATALOG = [
  {
    id: "g1", key: "timber_moisture_content", name: "Timber moisture content",
    type: "measurement", blocking: true, threshold: { min: 6, max: 9, unit: "%" },
    is_builtin: true,
  },
  {
    id: "g2", key: "site_noise_limit", name: "Site noise limit",
    type: "measurement", blocking: false, threshold: { max_db: 85 },
    is_builtin: false,
  },
  {
    id: "g3", key: "concrete_rh_astm_f2170", name: "Concrete rh astm f2170",
    type: "measurement", blocking: true,
    threshold: { max_rh_pct: 75, method: "ASTM F2170", configurable: true },
    is_builtin: true,
  },
];

const DETAIL = {
  ...CONFIGS[0],
  stages: [
    {
      id: "s1", key: "project_initiation", order: 1, name: "Project initiation",
      approver_role: "project_director",
      entry_gates: [
        { key: "loi_or_po", type: "document", label: "LOI or PO", blocking: true },
      ],
      quality_gates: [],
    },
    {
      id: "s2", key: "site_survey", order: 2, name: "Site survey",
      approver_role: null,
      entry_gates: [
        { key: "initiation_approved", type: "dependency",
          depends_on: "project_initiation", blocking: true },
      ],
      quality_gates: ["timber_moisture_content"],
    },
  ],
  gates: [
    {
      id: "r1", key: "timber_moisture_content", blocking: true,
      threshold: { min: 6, max: 9, unit: "%" },
    },
  ],
};

/** Routes every call the section/editor makes; records them for assertions. */
function stubApi(overrides: Record<string, unknown> = {}) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (init?.method && init.method !== "GET") return okJson({ data: { id: "new" } });
    if (href.includes("/gate-catalog")) return okJson({ data: CATALOG });
    if (/\/configurations\/[^/]+$/.test(href)) {
      return okJson({ data: overrides.detail ?? DETAIL });
    }
    return okJson({ data: overrides.configs ?? CONFIGS });
  });
}

const callsTo = (mock: ReturnType<typeof stubApi>, method: string) =>
  mock.mock.calls.filter(
    ([, o]) => (o as RequestInit | undefined)?.method === method,
  );

describe("ConfigurationsSection", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("lists configurations with their shape, version and status", async () => {
    vi.stubGlobal("fetch", stubApi());
    render(<ConfigurationsSection canWrite={true} />);

    await waitFor(() => expect(screen.getByText("Standard")).toBeInTheDocument());
    expect(screen.getByText("default")).toBeInTheDocument();
    expect(screen.getAllByText("built-in")).toHaveLength(2);
    expect(screen.getByText("inactive")).toBeInTheDocument();
    expect(screen.getByText(/Sequential · version 1/)).toBeInTheDocument();
    expect(screen.getByText(/Concurrent · version 1/)).toBeInTheDocument();
  });

  it("hides every mutating action from a read-only viewer", async () => {
    vi.stubGlobal("fetch", stubApi());
    render(<ConfigurationsSection canWrite={false} />);

    await waitFor(() => expect(screen.getByText("Standard")).toBeInTheDocument());
    expect(screen.queryByText("New configuration")).not.toBeInTheDocument();
    expect(screen.queryByText("Edit stages")).not.toBeInTheDocument();
    expect(screen.queryByText("Set default")).not.toBeInTheDocument();
  });

  it("offers Delete only for non-system configurations", async () => {
    vi.stubGlobal("fetch", stubApi());
    render(<ConfigurationsSection canWrite={true} />);

    await waitFor(() => expect(screen.getByText("Standard")).toBeInTheDocument());
    // only "Flooring — ASTM" is deletable; the two built-ins are not
    expect(screen.getAllByText("Delete")).toHaveLength(1);
  });

  it("sets a configuration as the default", async () => {
    const fetchMock = stubApi();
    vi.stubGlobal("fetch", fetchMock);
    render(<ConfigurationsSection canWrite={true} />);

    await waitFor(() => expect(screen.getByText("Concurrent")).toBeInTheDocument());
    fireEvent.click(screen.getAllByText("Set default")[0]);

    await waitFor(() => expect(callsTo(fetchMock, "PATCH")).toHaveLength(1));
    const [url, init] = callsTo(fetchMock, "PATCH")[0];
    expect(String(url)).toContain("/configurations/c2");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ is_default: true });
  });

  it("activates a deactivated configuration", async () => {
    const fetchMock = stubApi();
    vi.stubGlobal("fetch", fetchMock);
    render(<ConfigurationsSection canWrite={true} />);

    await waitFor(() => expect(screen.getByText("Activate")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Activate"));

    await waitFor(() => expect(callsTo(fetchMock, "PATCH")).toHaveLength(1));
    const body = JSON.parse(String((callsTo(fetchMock, "PATCH")[0][1] as RequestInit).body));
    expect(body).toEqual({ is_active: true });
  });

  it("surfaces a rejected action instead of silently failing", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        return okJson({
          error: { code: "VALIDATION_ERROR", message: "2 project(s) run on it" },
        }, 422);
      }
      return okJson({ data: CONFIGS });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("confirm", () => true);
    render(<ConfigurationsSection canWrite={true} />);

    await waitFor(() => expect(screen.getByText("Delete")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Delete"));

    await waitFor(() =>
      expect(screen.getByText(/2 project\(s\) run on it/)).toBeInTheDocument(),
    );
  });

  it("creates a configuration by cloning a base", async () => {
    const fetchMock = stubApi();
    vi.stubGlobal("fetch", fetchMock);
    render(<ConfigurationsSection canWrite={true} />);

    await waitFor(() => expect(screen.getByText("Standard")).toBeInTheDocument());
    fireEvent.click(screen.getByText("New configuration"));

    fireEvent.change(screen.getByLabelText(/Name/), {
      target: { value: "Flooring — ASTM" },
    });
    fireEvent.change(screen.getByLabelText(/Copy from/), { target: { value: "c2" } });
    fireEvent.click(screen.getByText("Create configuration"));

    await waitFor(() => expect(callsTo(fetchMock, "POST")).toHaveLength(1));
    const body = JSON.parse(String((callsTo(fetchMock, "POST")[0][1] as RequestInit).body));
    expect(body).toEqual({
      name: "Flooring — ASTM",
      base_configuration_id: "c2",
    });
  });
});

describe("ConfigurationEditor", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  const open = () =>
    render(
      <ConfigurationEditor
        configuration={{ id: "c1", name: "Standard" }}
        onDone={vi.fn()}
      />,
    );

  it("announces which version a save will publish", async () => {
    vi.stubGlobal("fetch", stubApi());
    open();
    await waitFor(() =>
      expect(screen.getByText(/Saving publishes version 2/)).toBeInTheDocument(),
    );
    expect(screen.getByText("Publish version 2")).toBeInTheDocument();
  });

  it("shows the fixed skeleton: every stage, with its order and approver", async () => {
    vi.stubGlobal("fetch", stubApi());
    open();

    await waitFor(() =>
      expect(screen.getByText("Project initiation")).toBeInTheDocument(),
    );
    expect(screen.getByText("Site survey")).toBeInTheDocument();
    // D2 — the skeleton is not editable, and the UI says so
    expect(screen.getByText(/The nine stages are fixed/)).toBeInTheDocument();
    expect(screen.getByText(/Approver position: Project director/)).toBeInTheDocument();
  });

  it("publishes documents, gates and shape as one full payload", async () => {
    const fetchMock = stubApi();
    vi.stubGlobal("fetch", fetchMock);
    open();

    await waitFor(() =>
      expect(screen.getByText("Project initiation")).toBeInTheDocument(),
    );

    // add a document to stage 1
    fireEvent.change(screen.getByLabelText(/Add a document to Project initiation/), {
      target: { value: "insurance certificate" },
    });
    fireEvent.click(screen.getByText("Add document"));

    // attach a gate to stage 1 — the gap this whole feature closes
    fireEvent.click(screen.getByLabelText("Site noise limit"));

    fireEvent.click(screen.getByText("Publish version 2"));

    await waitFor(() => expect(callsTo(fetchMock, "POST")).toHaveLength(1));
    const [url, init] = callsTo(fetchMock, "POST")[0];
    expect(String(url)).toContain("/configurations/c1/versions");

    const body = JSON.parse(String((init as RequestInit).body));
    expect(body.workflow_shape).toBe("sequential");
    expect(body.stages).toHaveLength(2);          // the full set, not just edits

    const stage1 = body.stages.find((s: { key: string }) => s.key === "project_initiation");
    expect(stage1.entry_documents.map((d: { key: string }) => d.key)).toEqual([
      "loi_or_po", "insurance_certificate",
    ]);
    expect(stage1.quality_gates).toEqual(["site_noise_limit"]);

    // the untouched stage keeps its gate; dependency gates are never sent
    const stage2 = body.stages.find((s: { key: string }) => s.key === "site_survey");
    expect(stage2.entry_documents).toEqual([]);
    expect(stage2.quality_gates).toEqual(["timber_moisture_content"]);

    // every attached gate carries its tuning
    expect(body.gates.map((g: { key: string }) => g.key).sort()).toEqual([
      "site_noise_limit", "timber_moisture_content",
    ]);
    const noise = body.gates.find((g: { key: string }) => g.key === "site_noise_limit");
    expect(noise.threshold).toEqual({ max_db: 85 });   // seeded from the catalog
  });

  it("retunes a threshold without touching the catalog", async () => {
    const fetchMock = stubApi();
    vi.stubGlobal("fetch", fetchMock);
    open();

    await waitFor(() => expect(screen.getByText("Site survey")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Site survey"));   // open stage 2

    fireEvent.change(await screen.findByLabelText("Max"), { target: { value: "8" } });
    fireEvent.click(screen.getByText("Publish version 2"));

    await waitFor(() => expect(callsTo(fetchMock, "POST")).toHaveLength(1));
    const body = JSON.parse(String((callsTo(fetchMock, "POST")[0][1] as RequestInit).body));
    const timber = body.gates.find(
      (g: { key: string }) => g.key === "timber_moisture_content",
    );
    expect(timber.threshold).toEqual({ min: 6, max: 8, unit: "%" });

    // the only POST is the version publish — the catalog is never written to (G-3)
    expect(callsTo(fetchMock, "POST")).toHaveLength(1);
  });

  it("preserves each threshold field's type when it is edited", async () => {
    // A threshold is free-form: numbers, strings and booleans live side by side.
    // Editing one must not turn `true` into "true" or 75 into "75" — the engine
    // compares readings against these values, so a retyped field stops evaluating.
    const detail = {
      ...DETAIL,
      stages: [
        {
          ...DETAIL.stages[0],
          quality_gates: ["concrete_rh_astm_f2170"],
        },
      ],
      gates: [
        {
          id: "r2", key: "concrete_rh_astm_f2170", blocking: true,
          threshold: { max_rh_pct: 75, method: "ASTM F2170", configurable: true },
        },
      ],
    };
    const fetchMock = stubApi({ detail });
    vi.stubGlobal("fetch", fetchMock);
    open();

    await waitFor(() =>
      expect(screen.getByLabelText("Max rh pct")).toBeInTheDocument(),
    );
    // a boolean renders as a checkbox, not a text box
    const configurable = screen.getByLabelText("Configurable");
    expect(configurable).toHaveAttribute("role", "checkbox");

    fireEvent.change(screen.getByLabelText("Max rh pct"), { target: { value: "70" } });
    fireEvent.change(screen.getByLabelText("Method"), { target: { value: "ASTM F1869" } });
    fireEvent.click(configurable);
    fireEvent.click(screen.getByText("Publish version 2"));

    await waitFor(() => expect(callsTo(fetchMock, "POST")).toHaveLength(1));
    const body = JSON.parse(String((callsTo(fetchMock, "POST")[0][1] as RequestInit).body));
    expect(body.gates[0].threshold).toEqual({
      max_rh_pct: 70,            // still a number
      method: "ASTM F1869",      // still a string
      configurable: false,       // still a boolean
    });
  });

  it("changes the workflow shape", async () => {
    const fetchMock = stubApi();
    vi.stubGlobal("fetch", fetchMock);
    open();

    await waitFor(() =>
      expect(screen.getByLabelText(/Workflow shape/)).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByLabelText(/Workflow shape/), {
      target: { value: "concurrent" },
    });
    expect(screen.getByText(/run in parallel/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Publish version 2"));
    await waitFor(() => expect(callsTo(fetchMock, "POST")).toHaveLength(1));
    const body = JSON.parse(String((callsTo(fetchMock, "POST")[0][1] as RequestInit).body));
    expect(body.workflow_shape).toBe("concurrent");
  });

  it("keeps a failed publish open with the reason shown", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return okJson({
          error: { code: "VALIDATION_ERROR", message: "Unknown quality gate(s): x" },
        }, 422);
      }
      if (String(url).includes("/gate-catalog")) return okJson({ data: CATALOG });
      return okJson({ data: DETAIL });
    });
    vi.stubGlobal("fetch", fetchMock);
    open();

    await waitFor(() =>
      expect(screen.getByText("Publish version 2")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText("Publish version 2"));

    await waitFor(() =>
      expect(screen.getByText(/Unknown quality gate\(s\): x/)).toBeInTheDocument(),
    );
    expect(screen.getByText("Publish version 2")).toBeInTheDocument();
  });
});
