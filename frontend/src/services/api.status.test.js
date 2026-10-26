import { describe, it, expect, vi, beforeEach } from "vitest";

// vi.mock is hoisted above plain variables, so the shared spy must be hoisted too.
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("axios", () => ({ default: { create: () => ({ get, post: vi.fn(), delete: vi.fn() }) } }));

import { getServerStatus } from "./api";

describe("getServerStatus", () => {
  beforeEach(() => vi.clearAllMocks());

  it("asks /status with the caller's timeout (a cold host can hold the first request for a minute)", async () => {
    get.mockResolvedValue({ data: { status: "ok", storage: { state: "ok" } } });
    await getServerStatus({ timeoutMs: 90000 });
    expect(get).toHaveBeenCalledWith("/status", { timeout: 90000 });
  });

  it("uses a long default timeout", async () => {
    get.mockResolvedValue({ data: { storage: { state: "ok" } } });
    await getServerStatus();
    expect(get.mock.calls[0][1].timeout).toBeGreaterThanOrEqual(60000);
  });

  it("returns ok and degraded storage with a known reason", async () => {
    get.mockResolvedValueOnce({ data: { storage: { state: "ok", since: "2026-10-26T10:00:00Z" } } });
    expect(await getServerStatus()).toEqual({ state: "ok" });
    get.mockResolvedValueOnce({ data: { storage: { state: "degraded", reason: "timeout" } } });
    expect(await getServerStatus()).toEqual({ state: "degraded", reason: "timeout" });
  });

  it("re-validates: an unknown reason becomes 'unknown', an unknown state becomes 'unmanaged'", async () => {
    get.mockResolvedValueOnce({ data: { storage: { state: "degraded", reason: "<script>x</script>" } } });
    expect(await getServerStatus()).toEqual({ state: "degraded", reason: "unknown" });
    get.mockResolvedValueOnce({ data: { storage: { state: "on fire" } } });
    expect(await getServerStatus()).toEqual({ state: "unmanaged" });
  });

  it.each([[null], [undefined], ["text"], [42], [{}], [{ storage: null }], [{ storage: "ok" }]])(
    "tolerates a malformed body (%o)", async (data) => {
      get.mockResolvedValue({ data });
      expect(await getServerStatus()).toEqual({ state: "unmanaged" });
    });

  it("lets network failures propagate so the hook can retry", async () => {
    get.mockRejectedValue(new Error("Network Error"));
    await expect(getServerStatus()).rejects.toThrow("Network Error");
  });
});
