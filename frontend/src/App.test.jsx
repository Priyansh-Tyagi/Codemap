import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("./services/api", () => ({ getServerStatus: vi.fn() }));
// Pages are stubs: this file tests the wiring (warm-up + banner + context), not the pages.
vi.mock("./pages/HomePage", () => ({ default: () => <div>home page</div> }));
vi.mock("./pages/ProjectPage", async () => {
  const ctx = await import("./hooks/serverStatusContext");
  return {
    default: function ProjectStub() {
      const status = ctx.useServerStatusContext();
      return <div data-testid="project">link may expire: {String(ctx.isStorageDegraded(status))}</div>;
    },
  };
});

import { getServerStatus } from "./services/api";
import App from "./App";

const advance = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
const renderApp = (path = "/") => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);

describe("App: warm-up, wake-up message and storage warning", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });
  afterEach(() => vi.useRealTimers());

  it("warms the server as soon as the page is open, and shows nothing if it answers fast", async () => {
    getServerStatus.mockResolvedValue({ state: "ok" });
    renderApp();
    expect(screen.getByText("home page")).toBeInTheDocument();
    await advance(1100);
    expect(getServerStatus).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("does not touch the server during the first second (drive-by loads must not wake it)", async () => {
    getServerStatus.mockResolvedValue({ state: "ok" });
    renderApp();
    await advance(900);
    expect(getServerStatus).not.toHaveBeenCalled();
    await advance(200);
    expect(getServerStatus).toHaveBeenCalledTimes(1);
  });

  it("shows the waking message while a cold server is slow, then removes it", async () => {
    let resolve;
    getServerStatus.mockReturnValue(new Promise((r) => (resolve = r)));
    renderApp();
    await advance(1000 + 2100);
    expect(screen.getByText("Waking the server…")).toBeInTheDocument();
    await act(async () => { resolve({ state: "ok" }); });
    expect(screen.queryByText("Waking the server…")).not.toBeInTheDocument();
  });

  it("also warms on a shared project link, not only the home page", async () => {
    getServerStatus.mockResolvedValue({ state: "ok" });
    renderApp("/p/abc");
    await advance(1100);
    expect(getServerStatus).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("project")).toBeInTheDocument();
  });

  it("tells the banner AND the pages when backup storage is offline", async () => {
    getServerStatus.mockResolvedValue({ state: "degraded", reason: "provider_refused" });
    renderApp("/p/abc");
    await advance(1100);
    expect(screen.getByText("Backup storage is offline")).toBeInTheDocument();
    expect(screen.getByTestId("project")).toHaveTextContent("link may expire: true");
  });

  it("pages see 'not degraded' while the server has not answered yet", async () => {
    getServerStatus.mockReturnValue(new Promise(() => {}));
    renderApp("/p/abc");
    await advance(500);
    expect(screen.getByTestId("project")).toHaveTextContent("link may expire: false");
  });
});
