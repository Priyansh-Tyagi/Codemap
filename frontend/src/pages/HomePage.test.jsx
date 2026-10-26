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


// --- Analyze while the free host is still waking up ---------------------------------
// Seen live: a request sent during the wake-up fails at once with no response, and
// the page printed "is it running on port 8000?". The page now holds the analysis and
// starts it by itself when the app-level status check says the server is up.
import { ServerStatusContext, DEFAULT_SERVER_STATUS } from "../hooks/serverStatusContext";

describe("HomePage: analyzing while the server wakes up", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getServerConfig.mockResolvedValue({ allowLocalPaths: false });
  });

  function tree(phase) {
    return (
      <ServerStatusContext.Provider value={{ ...DEFAULT_SERVER_STATUS, phase }}>
        <MemoryRouter initialEntries={["/"]}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/p/:projectId" element={<LocationProbe />} />
          </Routes>
        </MemoryRouter>
      </ServerStatusContext.Provider>
    );
  }

  async function submit(user, url = "https://github.com/pallets/flask") {
    await user.type(await screen.findByLabelText("Repository source"), url);
    await user.click(screen.getByRole("button", { name: "Analyze" }));
  }

  it("does not send the request while the server is waking, and says it is waiting", async () => {
    const user = userEvent.setup();
    render(tree("waking"));
    await submit(user);

    expect(analyzeRepository).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent(/analysis will start automatically/);
    expect(screen.getByRole("button", { name: /Waiting for server/ })).toBeDisabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("starts the held analysis exactly once, with the original input, when the server is ready", async () => {
    analyzeRepository.mockResolvedValue({ projectId: "p1", cached: false });
    const user = userEvent.setup();
    const { rerender } = render(tree("waking"));
    await submit(user);
    expect(analyzeRepository).not.toHaveBeenCalled();

    rerender(tree("ready"));
    await waitFor(() => expect(analyzeRepository).toHaveBeenCalledTimes(1));
    expect(analyzeRepository).toHaveBeenCalledWith({ githubUrl: "https://github.com/pallets/flask", forceRefresh: false });
    expect(await screen.findByTestId("probe")).toHaveTextContent("/p/p1");

    rerender(tree("ready"));                 // a later re-render must not run it again
    expect(analyzeRepository).toHaveBeenCalledTimes(1);
  });

  it("also holds a click made before the first status check has even started (idle)", async () => {
    analyzeRepository.mockResolvedValue({ projectId: "p2" });
    const user = userEvent.setup();
    const { rerender } = render(tree("idle"));
    await submit(user);
    expect(analyzeRepository).not.toHaveBeenCalled();
    rerender(tree("checking"));
    expect(analyzeRepository).not.toHaveBeenCalled();
    rerender(tree("ready"));
    await waitFor(() => expect(analyzeRepository).toHaveBeenCalledTimes(1));
  });

  it("gives up with a clear message, and never sends the request, if the server never answers", async () => {
    const user = userEvent.setup();
    const { rerender } = render(tree("waking"));
    await submit(user);
    rerender(tree("unreachable"));

    expect(await screen.findByRole("alert")).toHaveTextContent(/server isn't responding/);
    expect(analyzeRepository).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Analyze" })).toBeEnabled();     // can try again
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("sends immediately when the server is already up (no waiting, no extra note)", async () => {
    analyzeRepository.mockResolvedValue({ projectId: "p3" });
    const user = userEvent.setup();
    render(tree("ready"));
    await submit(user);
    await waitFor(() => expect(analyzeRepository).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/analysis will start automatically/)).not.toBeInTheDocument();
  });

  it("surfaces a real failure after the server is up (the held request is not swallowed)", async () => {
    analyzeRepository.mockRejectedValue({ response: { status: 400, data: { detail: "Branch or ref not found: x" } } });
    const user = userEvent.setup();
    const { rerender } = render(tree("waking"));
    await submit(user);
    rerender(tree("ready"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Branch or ref not found: x");
    expect(screen.getByRole("button", { name: "Analyze" })).toBeEnabled();
  });
});
