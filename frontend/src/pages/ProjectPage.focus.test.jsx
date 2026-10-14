import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";

vi.mock("../services/api", () => ({
  getProjectGraph: vi.fn(),
  getProjectSummary: vi.fn(),
  getProjectTour: vi.fn(),
}));
// The canvas is stubbed (jsdom has no layout engine). The stub exposes what the
// page hands it - node count, the re-fit key - and lets a test click nodes/pane.
vi.mock("../components/GraphView", async () => {
  const React = await import("react");
  return {
    default: React.forwardRef(function GraphViewStub({ nodes, fitKey, onNodeClick }, _ref) {
      return (
        <div>
          <div data-testid="graph" data-fitkey={fitKey}>{nodes.length} nodes</div>
          <div data-testid="graph-ids">{nodes.map((n) => n.id).sort().join(",")}</div>
          {nodes.map((n) => (
            <button key={n.id} data-testid={`canvas-node-${n.id}`} onClick={() => onNodeClick(n)} />
          ))}
          <button data-testid="canvas-pane" onClick={() => onNodeClick(null)} />
        </div>
      );
    }),
  };
});
vi.mock("../components/ImpactPanel", () => ({ default: () => null }));
vi.mock("../components/GuidedTour", () => ({ default: () => null }));
vi.mock("../services/auth", () => ({
  getCurrentUser: vi.fn().mockResolvedValue(null),
  logout: vi.fn(),
  redirectToGitHubLogin: vi.fn(),
}));

import { getProjectGraph, getProjectSummary, getProjectTour } from "../services/api";
import ProjectPage from "./ProjectPage";

/** Build a graph from ids + [source, target] pairs, with real in/out degrees. */
function buildGraph(ids, pairs) {
  const inDeg = Object.fromEntries(ids.map((i) => [i, 0]));
  const outDeg = Object.fromEntries(ids.map((i) => [i, 0]));
  for (const [s, t] of pairs) { outDeg[s]++; inDeg[t]++; }
  return {
    nodes: ids.map((id) => ({
      id, filePath: id, name: id.split("/").pop(), language: "javascript", linesOfCode: 10,
      inDegree: inDeg[id], outDegree: outDeg[id], dependencyDepth: 0, degreeCentrality: 0,
      betweennessCentrality: 0, inCycle: false, architectureType: "Util",
      riskScore: 5, riskLevel: "Low", riskReasons: [],
    })),
    edges: pairs.map(([source, target]) => ({ source, target, type: "import", symbols: [] })),
  };
}

const summary = {
  projectId: "abc", rootPath: "/r", sourceType: "github", sourceLabel: "owner/repo@main",
  fileCount: 0, edgeCount: 0, cycleCount: 0, highRiskCount: 0, avgDependencies: 0,
  createdAt: "2026-01-01T00:00:00Z",
};

// a -> b -> c -> d -> e
const CHAIN = buildGraph(["a.js", "b.js", "c.js", "d.js", "e.js"],
  [["a.js", "b.js"], ["b.js", "c.js"], ["c.js", "d.js"], ["d.js", "e.js"]]);

// 70 files: entry.tsx imports 5 of them, the other 64 are unrelated leaves
function bigGraph() {
  const leaves = Array.from({ length: 64 }, (_, i) => `leaf${String(i).padStart(2, "0")}.ts`);
  const used = ["u1.ts", "u2.ts", "u3.ts", "u4.ts", "u5.ts"];
  return buildGraph(["entry.tsx", ...used, ...leaves], used.map((u) => ["entry.tsx", u]));
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/p/abc"]}>
      <Routes><Route path="/p/:projectId" element={<ProjectPage />} /></Routes>
    </MemoryRouter>
  );
}

const focusBtn = () => screen.getByRole("button", { name: "Focus" });
const ids = () => screen.getByTestId("graph-ids").textContent;

describe("ProjectPage focus mode", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getProjectSummary.mockResolvedValue(summary);
  });

  it("small projects open on the full graph with Focus available but off", async () => {
    getProjectGraph.mockResolvedValue(CHAIN);
    renderPage();
    expect(await screen.findByTestId("graph")).toHaveTextContent("5 nodes");
    expect(focusBtn()).toHaveAttribute("aria-pressed", "false");
    expect(getProjectTour).not.toHaveBeenCalled();           // no extra request for small graphs
    expect(screen.getByTestId("graph")).toHaveAttribute("data-fitkey", "full");
  });

  it("turning Focus on with nothing selected starts somewhere sensible, at 1 hop", async () => {
    getProjectGraph.mockResolvedValue(CHAIN);
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("graph");

    await user.click(focusBtn());
    expect(focusBtn()).toHaveAttribute("aria-pressed", "true");
    expect(ids()).toBe("a.js,b.js");                          // the entry-like file + 1 hop
    expect(screen.getByText("Showing 2 of 5 files")).toBeInTheDocument();     // no "still large" hint for a small view
  });

  it("hop buttons widen the neighborhood", async () => {
    getProjectGraph.mockResolvedValue(CHAIN);
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("graph");
    await user.click(focusBtn());

    await user.click(screen.getByRole("button", { name: "2 hops" }));
    expect(ids()).toBe("a.js,b.js,c.js");
    await user.click(screen.getByRole("button", { name: "3 hops" }));
    expect(ids()).toBe("a.js,b.js,c.js,d.js");
    expect(screen.getByRole("button", { name: "3 hops" })).toHaveAttribute("aria-pressed", "true");
  });

  it("clicking another file re-centers the neighborhood on it", async () => {
    getProjectGraph.mockResolvedValue(CHAIN);
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("graph");
    await user.click(focusBtn());

    await user.click(screen.getByTestId("canvas-node-b.js"));
    expect(ids()).toBe("a.js,b.js,c.js");                     // b plus the files on both sides
  });

  it("clicking empty canvas in focus mode does NOT throw away the focused file", async () => {
    getProjectGraph.mockResolvedValue(CHAIN);
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("graph");
    await user.click(focusBtn());

    await user.click(screen.getByTestId("canvas-pane"));
    expect(ids()).toBe("a.js,b.js");
    expect(focusBtn()).toHaveAttribute("aria-pressed", "true");
  });

  it("the file tree still lists every file in focus mode, so any file is one click away", async () => {
    getProjectGraph.mockResolvedValue(CHAIN);
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("graph");
    await user.click(focusBtn());

    expect(ids()).toBe("a.js,b.js");
    await user.click(await screen.findByText("e.js"));        // a file far outside the neighborhood
    expect(ids()).toBe("d.js,e.js");
  });

  it("turning Focus off restores the whole graph and the full-view fit key", async () => {
    getProjectGraph.mockResolvedValue(CHAIN);
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("graph");
    await user.click(focusBtn());
    expect(screen.getByTestId("graph").dataset.fitkey).toMatch(/^focus:/);

    await user.click(focusBtn());
    expect(screen.getByTestId("graph")).toHaveTextContent("5 nodes");
    expect(screen.getByTestId("graph")).toHaveAttribute("data-fitkey", "full");
  });

  it("the fit key changes with the focused file and hop count (that is what re-frames the view)", async () => {
    getProjectGraph.mockResolvedValue(CHAIN);
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("graph");
    await user.click(focusBtn());
    const first = screen.getByTestId("graph").dataset.fitkey;

    await user.click(screen.getByRole("button", { name: "2 hops" }));
    const second = screen.getByTestId("graph").dataset.fitkey;
    await user.click(screen.getByTestId("canvas-node-c.js"));
    const third = screen.getByTestId("graph").dataset.fitkey;
    expect(new Set([first, second, third]).size).toBe(3);
  });

  describe("large projects", () => {
    it("open already focused on the tour's first entry point, never flashing the full graph", async () => {
      getProjectGraph.mockResolvedValue(bigGraph());
      getProjectTour.mockResolvedValue({ stops: [{ fileId: "entry.tsx", filePath: "entry.tsx", stage: "Entry points", reasons: [], members: [] }] });
      renderPage();

      // the very first graph render is already the focused one
      expect(await screen.findByTestId("graph")).toHaveTextContent("6 nodes");
      expect(getProjectTour).toHaveBeenCalledWith("abc", "trace");
      expect(focusBtn()).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByText(/Showing 6 of 70 files/)).toBeInTheDocument();
    });

    it("'Focus' toggled off shows all 70 files, and back on returns to the same file", async () => {
      getProjectGraph.mockResolvedValue(bigGraph());
      getProjectTour.mockResolvedValue({ stops: [{ fileId: "entry.tsx", filePath: "entry.tsx", stage: "Entry points", reasons: [], members: [] }] });
      const user = userEvent.setup();
      renderPage();
      await screen.findByTestId("graph");

      await user.click(focusBtn());
      expect(screen.getByTestId("graph")).toHaveTextContent("70 nodes");
      await user.click(focusBtn());
      expect(screen.getByTestId("graph")).toHaveTextContent("6 nodes");
    });

    it("falls back to the local heuristic when the tour request fails", async () => {
      getProjectGraph.mockResolvedValue(bigGraph());
      getProjectTour.mockRejectedValue(new Error("boom"));
      renderPage();
      expect(await screen.findByTestId("graph")).toHaveTextContent("6 nodes");   // entry.tsx chosen by heuristic
      expect(ids()).toContain("entry.tsx");
    });

    it("falls back when the tour names a file that isn't in the graph", async () => {
      getProjectGraph.mockResolvedValue(bigGraph());
      getProjectTour.mockResolvedValue({ stops: [{ fileId: "ghost.ts", filePath: "ghost.ts", stage: "x", reasons: [], members: [] }] });
      renderPage();
      expect(await screen.findByTestId("graph")).toHaveTextContent("6 nodes");
    });

    it("uses a grouped stop's member when the group's own id isn't a real file", async () => {
      getProjectGraph.mockResolvedValue(bigGraph());
      getProjectTour.mockResolvedValue({ stops: [{
        fileId: "group:8 files", filePath: "8 files used by x", stage: "Building blocks", reasons: [],
        members: [{ fileId: "u3.ts", filePath: "u3.ts" }],
      }] });
      renderPage();
      await screen.findByTestId("graph");
      expect(ids()).toContain("u3.ts");
      expect(ids()).toContain("entry.tsx");                   // u3's only neighbor
    });

    it("exactly at the threshold stays on the full graph", async () => {
      const exactly = buildGraph(Array.from({ length: 60 }, (_, i) => `f${i}.js`), []);
      getProjectGraph.mockResolvedValue(exactly);
      renderPage();
      expect(await screen.findByTestId("graph")).toHaveTextContent("60 nodes");
      expect(focusBtn()).toHaveAttribute("aria-pressed", "false");
      expect(getProjectTour).not.toHaveBeenCalled();
    });
  });

  it("a different project resets focus mode", async () => {
    getProjectGraph.mockResolvedValue(bigGraph());
    getProjectTour.mockResolvedValue({ stops: [{ fileId: "entry.tsx", filePath: "entry.tsx", stage: "e", reasons: [], members: [] }] });
    renderPage();
    await screen.findByTestId("graph");
    await waitFor(() => expect(focusBtn()).toHaveAttribute("aria-pressed", "true"));
  });
});
