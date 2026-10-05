import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";

vi.mock("../services/api", () => ({
  analyzeRepository: vi.fn(),
}));

import { analyzeRepository } from "../services/api";
import HomePage from "./HomePage";

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="probe">{loc.pathname}|{JSON.stringify(loc.state)}</div>;
}

function renderHome() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/p/:projectId" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("HomePage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("analyzes a local path, then navigates to the shareable /p/:id URL", async () => {
    analyzeRepository.mockResolvedValue({ projectId: "abc123", cached: false });
    const user = userEvent.setup();
    renderHome();

    await user.type(screen.getByLabelText("Repository source"), "/repo");
    await user.click(screen.getByRole("button", { name: "Analyze" }));

    expect(analyzeRepository).toHaveBeenCalledWith({ path: "/repo" });
    await waitFor(() =>
      expect(screen.getByTestId("probe")).toHaveTextContent("/p/abc123")
    );
  });

  it("sends githubUrl and forceRefresh in GitHub mode, and passes cached state along", async () => {
    analyzeRepository.mockResolvedValue({ projectId: "gh1", cached: true });
    const user = userEvent.setup();
    renderHome();

    await user.click(screen.getByRole("button", { name: "GitHub URL" }));
    await user.click(screen.getByLabelText("Force refresh"));
    await user.type(screen.getByLabelText("Repository source"), "https://github.com/o/r");
    await user.click(screen.getByRole("button", { name: "Analyze" }));

    expect(analyzeRepository).toHaveBeenCalledWith({
      githubUrl: "https://github.com/o/r",
      forceRefresh: true,
    });
    await waitFor(() =>
      expect(screen.getByTestId("probe")).toHaveTextContent('/p/gh1|{"cached":true}')
    );
  });

  it("shows the backend's error message and stays on the page", async () => {
    analyzeRepository.mockRejectedValue({ response: { data: { detail: "path does not exist: /nope" } } });
    const user = userEvent.setup();
    renderHome();

    await user.type(screen.getByLabelText("Repository source"), "/nope");
    await user.click(screen.getByRole("button", { name: "Analyze" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("path does not exist: /nope");
    expect(screen.queryByTestId("probe")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze" })).toBeEnabled();
  });

  it("falls back to a backend-unreachable message when there is no response", async () => {
    analyzeRepository.mockRejectedValue(new Error("Network Error"));
    const user = userEvent.setup();
    renderHome();

    await user.type(screen.getByLabelText("Repository source"), "/repo");
    await user.click(screen.getByRole("button", { name: "Analyze" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't reach the backend");
  });

  it("does not call the API for blank input", async () => {
    const user = userEvent.setup();
    renderHome();

    await user.type(screen.getByLabelText("Repository source"), "   ");
    await user.click(screen.getByRole("button", { name: "Analyze" }));

    expect(analyzeRepository).not.toHaveBeenCalled();
  });

  it("reports a bare server 500 as a server error, not as 'backend unreachable'", async () => {
    analyzeRepository.mockRejectedValue({ response: { status: 500, data: "Internal Server Error" } });
    const user = userEvent.setup();
    renderHome();

    await user.type(screen.getByLabelText("Repository source"), "https://github.com/o/r");
    await user.click(screen.getByRole("button", { name: "Analyze" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("server returned an error (500)");
    expect(alert).not.toHaveTextContent("Couldn't reach");
  });
});
