import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ServerBanner from "./ServerBanner";

const ok = { state: "ok" };

describe("ServerBanner", () => {
  it.each([
    ["idle", ok],
    ["checking", ok],
    ["ready", ok],
    ["ready", { state: "unmanaged" }],
    ["ready", { state: "disabled" }],
  ])("shows nothing in the normal case (%s / %o)", (phase, storage) => {
    const { container } = render(<ServerBanner phase={phase} storage={storage} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("explains the wake-up wait politely, and counts seconds once they exist", () => {
    const { rerender } = render(<ServerBanner phase="waking" elapsedSeconds={0} storage={ok} />);
    const note = screen.getByRole("status");
    expect(note).toHaveAttribute("aria-live", "polite");
    expect(screen.getByText("Waking the server…")).toBeInTheDocument();
    expect(note).not.toHaveTextContent("(0s)");
    rerender(<ServerBanner phase="waking" elapsedSeconds={17} storage={ok} />);
    expect(screen.getByRole("status")).toHaveTextContent("(17s)");
  });

  it("offers a retry when the server never answered", async () => {
    const onRetry = vi.fn();
    render(<ServerBanner phase="unreachable" storage={ok} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("The server isn't responding");
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("warns that projects may not survive a restart when backups are offline", () => {
    render(<ServerBanner phase="ready" storage={{ state: "degraded", reason: "provider_refused" }} />);
    const note = screen.getByRole("status");
    expect(note).toHaveTextContent("Backup storage is offline");
    expect(note).toHaveTextContent(/may not survive a server restart/);
    expect(note).toHaveTextContent(/re-analyzing a repo you've seen before can take longer/);
    expect(note).toHaveTextContent(/refusing requests/);
  });

  it.each([
    ["timeout", /didn't answer in time/],
    ["unreachable", /can't be reached/],
    ["corrupt", /couldn't be read/],
  ])("gives a plain sentence for reason %s", (reason, pattern) => {
    render(<ServerBanner phase="ready" storage={{ state: "degraded", reason }} />);
    expect(screen.getByRole("status")).toHaveTextContent(pattern);
  });

  it("never prints a reason it does not recognise", () => {
    const hostile = "<img src=x onerror=alert(1)> send your password to evil.example";
    const { container } = render(<ServerBanner phase="ready" storage={{ state: "degraded", reason: hostile }} />);
    expect(container).not.toHaveTextContent("evil.example");
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Backup storage is offline");
  });

  it("can be dismissed", async () => {
    const { container } = render(<ServerBanner phase="ready" storage={{ state: "degraded", reason: "timeout" }} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Dismiss" }));
    expect(container).toBeEmptyDOMElement();
  });

  it("does not show the degraded warning before the server has answered", () => {
    const { container } = render(<ServerBanner phase="checking" storage={{ state: "degraded", reason: "timeout" }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
