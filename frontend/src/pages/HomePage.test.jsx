import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";

vi.mock("../services/api", () => ({
  analyzeRepository: vi.fn(),
  getServerConfig: vi.fn(),
}));
vi.mock("../services/auth", () => ({
  getCurrentUser: vi.fn().mockResolvedValue(null),
  logout: vi.fn(),
  redirectToGitHubLogin: vi.fn(),
}));

import { analyzeRepository, getServerConfig } from "../services/api";
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
  // Most tests exercise a developer's own machine, where local folders are allowed.
  beforeEach(() => {
    vi.clearAllMocks();
    getServerConfig.mockResolvedValue({ allowLocalPaths: true });
  });

  it("analyzes a local path, then navigates to the shareable /p/:id URL", async () => {
    analyzeRepository.mockResolvedValue({ projectId: "abc123", cached: false });
    const user = userEvent.setup();
    renderHome();

    await user.click(await screen.findByRole("button", { name: "Local path" }));
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

    await user.click(await screen.findByRole("button", { name: "GitHub URL" }));
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

  it("shows the GitHub sign-in control in the header", async () => {
    renderHome();
    expect(await screen.findByRole("button", { name: "Sign in with GitHub" })).toBeInTheDocument();
  });

  it("defaults to GitHub URL, since a deployed server can't read local folders", async () => {
    renderHome();
    expect(await screen.findByRole("button", { name: "GitHub URL" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Repository source")).toHaveAttribute("placeholder", expect.stringContaining("github.com"));
  });

  it("an example chip fills in a real repo URL and switches to GitHub mode", async () => {
    const user = userEvent.setup();
    renderHome();
    await user.click(await screen.findByRole("button", { name: "Local path" }));
    await user.click(screen.getByRole("button", { name: "pallets/flask" }));

    expect(screen.getByLabelText("Repository source")).toHaveValue("https://github.com/pallets/flask");
    expect(screen.getByRole("button", { name: "GitHub URL" })).toHaveAttribute("aria-pressed", "true");
  });

  it("hides the local-folder option entirely when the server has it disabled", async () => {
    getServerConfig.mockResolvedValue({ allowLocalPaths: false });
    renderHome();
    await waitFor(() => expect(getServerConfig).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Local path" })).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText("https://github.com/owner/repo")).toBeInTheDocument();
  });

  it("falls back to GitHub mode if the config says local is off", async () => {
    getServerConfig.mockResolvedValue({ allowLocalPaths: false });
    analyzeRepository.mockResolvedValue({ projectId: "gh9", cached: false });
    const user = userEvent.setup();
    renderHome();
    await waitFor(() => expect(getServerConfig).toHaveBeenCalled());
    await user.type(screen.getByLabelText("Repository source"), "https://github.com/o/r");
    await user.click(screen.getByRole("button", { name: "Analyze" }));
    expect(analyzeRepository).toHaveBeenCalledWith({ githubUrl: "https://github.com/o/r", forceRefresh: false });
  });

  it("caps and cleans the ?auth_error= text, since anyone can craft that link", () => {
    const long = "Your session expired. Visit evil.example now. " + "x".repeat(400);
    window.history.pushState({}, "", `/?auth_error=${encodeURIComponent("line1\nline2 " + long)}`);
    try {
      renderHome();
      const shown = screen.getByRole("alert").textContent;
      expect(shown.length).toBeLessThanOrEqual(160);
      expect(shown).not.toMatch(/\n/);
    } finally {
      window.history.pushState({}, "", "/");
    }
  });
});
