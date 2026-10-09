import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../services/api", () => ({
  getProjectTour: vi.fn(),
  narrateProjectTour: vi.fn(),
}));

import { getProjectTour, narrateProjectTour } from "../services/api";
import GuidedTour from "./GuidedTour";

const stop = (fileId, stage, reasons = [], extra = {}) => ({
  fileId, filePath: fileId, stage, reasons, members: [], narrative: null, ...extra,
});
const tour = (stops, extra = {}) => ({ stops, mode: "trace", note: null, narrated: false, ...extra });
const setup = (props = {}) =>
  render(<GuidedTour projectId="abc" onSelectFile={vi.fn()} onClose={vi.fn()} {...props} />);

describe("GuidedTour", () => {
  beforeEach(() => vi.clearAllMocks());

  it("loads the deterministic tour grouped by stage, with zero AI involved", async () => {
    getProjectTour.mockResolvedValue(tour([
      stop("src/routes.py", "Entry points", ["Nothing else imports it"]),
      stop("src/utils.py", "Building blocks", ["2 other files depend on this"]),
    ]));
    setup();

    expect(await screen.findByText("routes.py")).toBeInTheDocument();
    expect(screen.getByText("Entry points")).toBeInTheDocument();
    expect(screen.getByText("Building blocks")).toBeInTheDocument();
    expect(screen.getByText("2 other files depend on this")).toBeInTheDocument();
    expect(getProjectTour).toHaveBeenCalledWith("abc", "trace");
    expect(narrateProjectTour).not.toHaveBeenCalled();
  });

  it("shows the filename first and the folder separately, so nothing important is truncated", async () => {
    getProjectTour.mockResolvedValue(tour([stop("PitSynapse/frontend/src/components/ControlPanel.jsx", "Building blocks")]));
    setup();
    expect(await screen.findByText("ControlPanel.jsx")).toBeInTheDocument();
    expect(screen.getByText("PitSynapse/frontend/src/components")).toBeInTheDocument();
  });

  it("switching direction refetches in that mode", async () => {
    getProjectTour.mockResolvedValue(tour([stop("a.py", "Entry points")]));
    const user = userEvent.setup();
    setup();
    await screen.findByText("a.py");

    await user.click(screen.getByRole("button", { name: "Core first" }));
    expect(getProjectTour).toHaveBeenLastCalledWith("abc", "foundation");
    expect(screen.getByRole("button", { name: "Core first" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Top-down" })).toHaveAttribute("aria-pressed", "false");
  });

  it("renders a grouped stop as one heading with clickable members", async () => {
    getProjectTour.mockResolvedValue(tour([
      stop("c0.jsx", "Building blocks", [], {
        filePath: "3 files used by Dashboard.jsx",
        members: [
          { fileId: "src/c0.jsx", filePath: "src/c0.jsx" },
          { fileId: "src/c1.jsx", filePath: "src/c1.jsx" },
          { fileId: "src/c2.jsx", filePath: "src/c2.jsx" },
        ],
      }),
    ]));
    const onSelectFile = vi.fn();
    const user = userEvent.setup();
    setup({ onSelectFile });

    expect(await screen.findByText("3 files used by Dashboard.jsx")).toBeInTheDocument();
    await user.click(screen.getByText("c1.jsx"));
    expect(onSelectFile).toHaveBeenCalledWith("src/c1.jsx");
  });

  it("clicking a stop calls onSelectFile with that file's id", async () => {
    getProjectTour.mockResolvedValue(tour([stop("src/a.py", "Entry points")]));
    const onSelectFile = vi.fn();
    const user = userEvent.setup();
    setup({ onSelectFile });
    await user.click(await screen.findByText("a.py"));
    expect(onSelectFile).toHaveBeenCalledWith("src/a.py");
  });

  it("shows the note about files left out of the tour", async () => {
    getProjectTour.mockResolvedValue(tour([stop("a.py", "Entry points")], {
      note: "18 other files have no import connections to the rest of the project",
    }));
    setup();
    expect(await screen.findByText(/18 other files have no import connections/)).toBeInTheDocument();
  });

  it("explains why the tour is empty instead of showing a blank panel", async () => {
    getProjectTour.mockResolvedValue(tour([], { note: "No import connections were found between these files." }));
    setup();
    expect(await screen.findByText(/No import connections were found/)).toBeInTheDocument();
  });

  it("narration is opt-in, passes the current mode, and attaches narratives", async () => {
    getProjectTour.mockResolvedValue(tour([stop("src/a.py", "Entry points")]));
    narrateProjectTour.mockResolvedValue(tour(
      [stop("src/a.py", "Entry points", [], { narrative: "This is where the app starts." })],
      { narrated: true },
    ));
    const user = userEvent.setup();
    setup();

    await user.click(await screen.findByRole("button", { name: "✨ Narrate with AI" }));
    expect(narrateProjectTour).toHaveBeenCalledWith("abc", "trace");
    expect(await screen.findByText("This is where the app starts.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "✨ Narrate with AI" })).not.toBeInTheDocument();
  });

  it("changing direction clears narration so it can't describe the wrong stops", async () => {
    getProjectTour.mockResolvedValue(tour([stop("src/a.py", "Entry points")]));
    narrateProjectTour.mockResolvedValue(tour(
      [stop("src/a.py", "Entry points", [], { narrative: "Narrated." })], { narrated: true },
    ));
    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: "✨ Narrate with AI" }));
    await screen.findByText("Narrated.");

    await user.click(screen.getByRole("button", { name: "Core first" }));
    expect(await screen.findByRole("button", { name: "✨ Narrate with AI" })).toBeInTheDocument();
    expect(screen.queryByText("Narrated.")).not.toBeInTheDocument();
  });

  it("a graceful AI failure keeps the deterministic stops and shows an inline notice", async () => {
    getProjectTour.mockResolvedValue(tour([stop("src/a.py", "Entry points", ["notable"])]));
    narrateProjectTour.mockResolvedValue(tour([stop("src/a.py", "Entry points", ["notable"])], {
      narrationError: "AI narration is not configured on this server.",
    }));
    const user = userEvent.setup();
    setup();

    await user.click(await screen.findByRole("button", { name: "✨ Narrate with AI" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not configured on this server");
    expect(screen.getByText("a.py")).toBeInTheDocument();
    expect(screen.getByText("notable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "✨ Narrate with AI" })).toBeInTheDocument();
  });

  it("a failed narrate request still doesn't break the panel", async () => {
    getProjectTour.mockResolvedValue(tour([stop("src/a.py", "Entry points")]));
    narrateProjectTour.mockRejectedValue(new Error("Network Error"));
    const user = userEvent.setup();
    setup();
    await user.click(await screen.findByRole("button", { name: "✨ Narrate with AI" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't reach the backend");
    expect(screen.getByText("a.py")).toBeInTheDocument();
  });

  it("the close button calls onClose", async () => {
    getProjectTour.mockResolvedValue(tour([]));
    const onClose = vi.fn();
    const user = userEvent.setup();
    setup({ onClose });
    await user.click(await screen.findByRole("button", { name: "Close guided tour" }));
    expect(onClose).toHaveBeenCalled();
  });
});
