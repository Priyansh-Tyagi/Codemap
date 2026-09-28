import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

vi.mock("../services/api", () => ({
  getProjectGraph: vi.fn(),
  getProjectSummary: vi.fn(),
}));
// React Flow needs real browser layout APIs jsdom lacks; the page logic is
// what's under test here, so stub the canvas and the network-backed panel.
vi.mock("../components/GraphView", async () => {
  const React = await import("react");
  return {
    default: React.forwardRef(function GraphViewStub({ nodes }, _ref) {
      return <div data-testid="graph">{nodes.length} nodes</div>;
    }),
  };
});
vi.mock("../components/ImpactPanel", () => ({ default: () => null }));

import { getProjectGraph, getProjectSummary } from "../services/api";
import ProjectPage from "./ProjectPage";

const node = (id) => ({
  id, filePath: id, name: id.split("/").pop(), language: "javascript", linesOfCode: 10,
  inDegree: 0, outDegree: 0, dependencyDepth: 0, degreeCentrality: 0,
  betweennessCentrality: 0, inCycle: false, architectureType: "Util",
  riskScore: 5, riskLevel: "Low", riskReasons: [],
});

const summary = {
  projectId: "abc", rootPath: "/r", sourceType: "github", sourceLabel: "owner/repo@main",
  fileCount: 2, edgeCount: 1, cycleCount: 0, highRiskCount: 0, avgDependencies: 0.5,
  createdAt: "2026-01-01T00:00:00Z",
};

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<div>home</div>} />
        <Route path="/p/:projectId" element={<ProjectPage />} />
      </Routes>
    </MemoryRouter>
  );
}

function mockClipboard(writeText) {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText }, configurable: true,
  });
}

describe("ProjectPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetches by the URL param (works for a freshly shared link) and renders the project", async () => {
    getProjectGraph.mockResolvedValue({ nodes: [node("src/a.js"), node("src/b.js")], edges: [] });
    getProjectSummary.mockResolvedValue(summary);
    renderAt("/p/shared-id-42");

    expect(screen.getByText("Loading project…")).toBeInTheDocument();
    expect(await screen.findByTestId("graph")).toHaveTextContent("2 nodes");
    expect(getProjectGraph).toHaveBeenCalledWith("shared-id-42");
    expect(getProjectSummary).toHaveBeenCalledWith("shared-id-42");
    expect(screen.getByText("owner/repo@main")).toBeInTheDocument();
  });

  it("shows a friendly not-found state with a way home on 404", async () => {
    getProjectGraph.mockRejectedValue({ response: { status: 404 } });
    getProjectSummary.mockRejectedValue({ response: { status: 404 } });
    renderAt("/p/stale-id");

    expect(await screen.findByText("Project not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Analyze a repository" })).toHaveAttribute("href", "/");
  });

  it("distinguishes a backend outage from a missing project", async () => {
    getProjectGraph.mockRejectedValue(new Error("Network Error"));
    getProjectSummary.mockRejectedValue(new Error("Network Error"));
    renderAt("/p/abc");

    expect(await screen.findByText(/Couldn't reach the backend/)).toBeInTheDocument();
    expect(screen.queryByText("Project not found")).not.toBeInTheDocument();
  });

  it("copies the current URL and shows a confirmation", async () => {
    getProjectGraph.mockResolvedValue({ nodes: [node("a.js")], edges: [] });
    getProjectSummary.mockResolvedValue(summary);
    const writeText = vi.fn().mockResolvedValue(undefined);
    mockClipboard(writeText);
    renderAt("/p/abc");

    fireEvent.click(await screen.findByRole("button", { name: "Copy link" }));

    expect(writeText).toHaveBeenCalledWith(window.location.href);
    expect(await screen.findByRole("button", { name: "Copied!" })).toBeInTheDocument();
  });

  it("tells the user when the clipboard is unavailable instead of failing silently", async () => {
    getProjectGraph.mockResolvedValue({ nodes: [node("a.js")], edges: [] });
    getProjectSummary.mockResolvedValue(summary);
    mockClipboard(vi.fn().mockRejectedValue(new Error("denied")));
    renderAt("/p/abc");

    fireEvent.click(await screen.findByRole("button", { name: "Copy link" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't copy");
    expect(screen.queryByRole("button", { name: "Copied!" })).not.toBeInTheDocument();
  });

  it("shows an empty-project message when no supported files were found", async () => {
    getProjectGraph.mockResolvedValue({ nodes: [], edges: [] });
    getProjectSummary.mockResolvedValue({ ...summary, fileCount: 0 });
    renderAt("/p/abc");

    await waitFor(() =>
      expect(screen.getByText(/No JavaScript, TypeScript, or Python files/)).toBeInTheDocument()
    );
  });
});
