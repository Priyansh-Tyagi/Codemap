import { describe, it, expect } from "vitest";
import { describeApiError } from "./apiError";

describe("describeApiError", () => {
  it("says the backend is unreachable only when there was no response", () => {
    expect(describeApiError(new Error("Network Error"))).toMatch(/Couldn't reach the backend/);
  });
  it("explains that an idle host may still be waking up, and keeps the local-dev hint", () => {
    const msg = describeApiError(new Error("Network Error"));
    expect(msg).toMatch(/waking up/);
    expect(msg).toMatch(/up to a minute/);
    expect(msg).toMatch(/port 8000/);                      // still useful on a developer's machine
  });
  it.each([502, 503, 504])("treats a gateway %i as 'starting up', not as a code bug", (status) => {
    const msg = describeApiError({ response: { status, data: "<html>Bad gateway</html>" } });
    expect(msg).toMatch(/starting up or temporarily unavailable/);
    expect(msg).not.toMatch(/Check the backend log/);
  });
  it("still prefers the server's own message on a 503 that carries one", () => {
    expect(describeApiError({ response: { status: 503, data: { detail: "Maintenance" } } })).toBe("Maintenance");
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
