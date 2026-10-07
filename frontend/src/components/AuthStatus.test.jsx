import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../services/auth", () => ({
  getCurrentUser: vi.fn(),
  logout: vi.fn(),
  redirectToGitHubLogin: vi.fn(),
}));

import { getCurrentUser, logout, redirectToGitHubLogin } from "../services/auth";
import AuthStatus from "./AuthStatus";

describe("AuthStatus", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows nothing while the sign-in check is in flight, to avoid a flash", async () => {
    let resolve;
    getCurrentUser.mockReturnValue(new Promise((r) => (resolve = r)));
    const { container } = render(<AuthStatus />);
    expect(container).toBeEmptyDOMElement();
    resolve(null);
    await waitFor(() => expect(container).not.toBeEmptyDOMElement());
  });

  it("shows a sign-in button when signed out, and it redirects on click", async () => {
    getCurrentUser.mockResolvedValue(null);
    const user = userEvent.setup();
    render(<AuthStatus />);

    const btn = await screen.findByRole("button", { name: "Sign in with GitHub" });
    await user.click(btn);
    expect(redirectToGitHubLogin).toHaveBeenCalled();
  });

  it("shows the username and avatar when signed in", async () => {
    getCurrentUser.mockResolvedValue({ login: "octocat", avatarUrl: "https://example.com/a.png" });
    render(<AuthStatus />);

    expect(await screen.findByText("octocat")).toBeInTheDocument();
    expect(screen.getByRole("img")).toHaveAttribute("src", "https://example.com/a.png");
  });

  it("signs out and flips back to the sign-in button", async () => {
    getCurrentUser.mockResolvedValue({ login: "octocat", avatarUrl: null });
    logout.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<AuthStatus />);

    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(logout).toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: "Sign in with GitHub" })).toBeInTheDocument();
  });

  it("treats a failed /auth/me check as signed out rather than erroring", async () => {
    getCurrentUser.mockRejectedValue(new Error("network"));
    render(<AuthStatus />);
    expect(await screen.findByRole("button", { name: "Sign in with GitHub" })).toBeInTheDocument();
  });
});
