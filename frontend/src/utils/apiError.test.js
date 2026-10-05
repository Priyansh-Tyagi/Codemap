import { describe, it, expect } from "vitest";
import { describeApiError } from "./apiError";

describe("describeApiError", () => {
  it("says the backend is unreachable only when there was no response", () => {
    expect(describeApiError(new Error("Network Error"))).toMatch(/Couldn't reach the backend/);
  });
  it("uses the server's own message when it sent one", () => {
    const err = { response: { status: 400, data: { detail: "Branch or ref not found: x" } } };
    expect(describeApiError(err)).toBe("Branch or ref not found: x");
  });
  it("does NOT claim the backend is unreachable for a bare 500", () => {
    const msg = describeApiError({ response: { status: 500, data: "Internal Server Error" } });
    expect(msg).toMatch(/server returned an error \(500\)/);
    expect(msg).not.toMatch(/reach/);
  });
  it("handles FastAPI validation error arrays", () => {
    const err = { response: { status: 422, data: { detail: [{ msg: "field required" }] } } };
    expect(describeApiError(err)).toBe("field required");
  });
});
