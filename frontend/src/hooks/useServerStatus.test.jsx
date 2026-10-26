import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

vi.mock("../services/api", () => ({ getServerStatus: vi.fn() }));
import { getServerStatus } from "../services/api";
import { useServerStatus, STATUS_DEFAULTS } from "./useServerStatus";

// Fast, deterministic timing: every real wait in the hook is shrunk to a few
// hundred ms so a "cold start" and a "gave up" both play out in a few steps.
const FAST = { startDelayMs: 100, wakingAfterMs: 200, requestTimeoutMs: 5000, retryDelayMs: 300, giveUpAfterMs: 2000 };

function trackPhases(options = FAST) {
  const phases = [];
  const view = renderHook(() => {
    const s = useServerStatus(options);
    if (phases[phases.length - 1] !== s.phase) phases.push(s.phase);
    return s;
  });
  return { ...view, phases };
}

const advance = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

describe("useServerStatus", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });
  afterEach(() => vi.useRealTimers());

  it("waits before the first request so drive-by loads don't wake the server", async () => {
    getServerStatus.mockResolvedValue({ state: "ok" });
    trackPhases();
    await advance(99);
    expect(getServerStatus).not.toHaveBeenCalled();
    await advance(2);
    expect(getServerStatus).toHaveBeenCalledTimes(1);
  });

  it("asks the server with the long cold-start timeout", async () => {
    getServerStatus.mockResolvedValue({ state: "ok" });
    trackPhases();
    await advance(150);
    expect(getServerStatus).toHaveBeenCalledWith({ timeoutMs: 5000 });
  });

  it("a warm server goes straight to ready and never shows the waking state", async () => {
    getServerStatus.mockResolvedValue({ state: "ok" });
    const { result, phases } = trackPhases();
    await advance(500);
    expect(result.current.phase).toBe("ready");
    expect(result.current.storage).toEqual({ state: "ok" });
    expect(phases).not.toContain("waking");
  });

  it("a slow (cold) server shows waking after the threshold, counts seconds, then becomes ready", async () => {
    let resolve;
    getServerStatus.mockReturnValue(new Promise((r) => (resolve = r)));
    const { result, phases } = trackPhases();
    await advance(100 + 150);
    expect(result.current.phase).toBe("checking");
    await advance(100);
    expect(result.current.phase).toBe("waking");

    await advance(3000);
    expect(result.current.elapsedSeconds).toBeGreaterThanOrEqual(3);

    await act(async () => { resolve({ state: "ok" }); });
    expect(result.current.phase).toBe("ready");
    expect(phases).toEqual(["idle", "checking", "waking", "ready"]);
  });

  it("makes no further requests once ready", async () => {
    getServerStatus.mockResolvedValue({ state: "ok" });
    trackPhases();
    await advance(500);
    await advance(120000);
    expect(getServerStatus).toHaveBeenCalledTimes(1);
  });

  it("stops counting seconds once ready", async () => {
    getServerStatus.mockResolvedValue({ state: "ok" });
    const { result } = trackPhases();
    await advance(500);
    const frozen = result.current.elapsedSeconds;
    await advance(10000);
    expect(result.current.elapsedSeconds).toBe(frozen);
  });

  it("retries after a failure and recovers", async () => {
    getServerStatus
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockRejectedValueOnce(new Error("502"))
      .mockResolvedValue({ state: "ok" });
    const { result } = trackPhases();
    await advance(100);
    expect(getServerStatus).toHaveBeenCalledTimes(1);
    await advance(300);
    expect(getServerStatus).toHaveBeenCalledTimes(2);
    await advance(300);
    expect(getServerStatus).toHaveBeenCalledTimes(3);
    expect(result.current.phase).toBe("ready");
  });

  it("gives up after the limit instead of retrying forever, then Retry starts over", async () => {
    getServerStatus.mockRejectedValue(new Error("Network Error"));
    const { result, phases } = trackPhases();
    // Step in small increments: one big jump lets React batch the phases together.
    await advance(150);
    await advance(300);
    expect(result.current.phase).toBe("waking");
    await advance(2000);
    expect(result.current.phase).toBe("unreachable");
    expect(phases).toEqual(["idle", "checking", "waking", "unreachable"]);

    const callsWhenGivenUp = getServerStatus.mock.calls.length;
    await advance(20000);
    expect(getServerStatus.mock.calls.length).toBe(callsWhenGivenUp);   // really stopped

    getServerStatus.mockResolvedValue({ state: "ok" });
    act(() => result.current.retry());
    await advance(300);
    expect(result.current.phase).toBe("ready");
  });

  it("passes degraded storage through, reason included", async () => {
    getServerStatus.mockResolvedValue({ state: "degraded", reason: "provider_refused" });
    const { result } = trackPhases();
    await advance(500);
    expect(result.current.phase).toBe("ready");
    expect(result.current.storage).toEqual({ state: "degraded", reason: "provider_refused" });
  });

  it("does nothing after unmount: no state updates, no more requests", async () => {
    let resolve;
    getServerStatus.mockReturnValue(new Promise((r) => (resolve = r)));
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const { unmount } = trackPhases();
    await advance(150);
    expect(getServerStatus).toHaveBeenCalledTimes(1);
    unmount();
    await act(async () => { resolve({ state: "ok" }); });
    await advance(60000);
    expect(getServerStatus).toHaveBeenCalledTimes(1);
    expect(errors).not.toHaveBeenCalled();
    errors.mockRestore();
  });

  it("a request that FAILS after unmount does not start a retry loop", async () => {
    let reject;
    getServerStatus.mockReturnValue(new Promise((_, r) => (reject = r)));
    const { unmount } = trackPhases();
    await advance(150);
    expect(getServerStatus).toHaveBeenCalledTimes(1);
    unmount();
    await act(async () => { reject(new Error("Network Error")); });
    await advance(60000);
    expect(getServerStatus).toHaveBeenCalledTimes(1);
  });

  it("the real defaults keep the grace period, the long cold-start timeout and a bounded retry", () => {
    expect(STATUS_DEFAULTS.startDelayMs).toBeGreaterThanOrEqual(500);       // drive-by loads must not wake the host
    expect(STATUS_DEFAULTS.requestTimeoutMs).toBeGreaterThanOrEqual(60000); // a cold host can hold the first request ~1 min
    expect(STATUS_DEFAULTS.giveUpAfterMs).toBeLessThanOrEqual(600000);      // never retry forever
    expect(STATUS_DEFAULTS.retryDelayMs).toBeGreaterThanOrEqual(1000);      // never hammer the server
  });

  it("an unmount during the retry wait cancels the retry", async () => {
    getServerStatus.mockRejectedValue(new Error("down"));
    const { unmount } = trackPhases();
    await advance(150);
    expect(getServerStatus).toHaveBeenCalledTimes(1);
    unmount();
    await advance(10000);
    expect(getServerStatus).toHaveBeenCalledTimes(1);
  });
});
