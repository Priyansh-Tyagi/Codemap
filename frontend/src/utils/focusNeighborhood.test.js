import { describe, it, expect } from "vitest";
import { neighborhoodIds, pickFocusStart, LARGE_GRAPH_THRESHOLD } from "./focusNeighborhood";

const e = (source, target) => ({ source, target });
// a -> b -> c -> d -> e   (a chain)
const chain = [e("a", "b"), e("b", "c"), e("c", "d"), e("d", "e")];

const n = (id, inDegree, outDegree) => ({ id, inDegree, outDegree });

describe("neighborhoodIds", () => {
  it("0 hops is just the root", () => {
    expect([...neighborhoodIds(chain, "c", 0)]).toEqual(["c"]);
  });

  it("grows one import-step per hop", () => {
    expect([...neighborhoodIds(chain, "a", 1)].sort()).toEqual(["a", "b"]);
    expect([...neighborhoodIds(chain, "a", 2)].sort()).toEqual(["a", "b", "c"]);
    expect([...neighborhoodIds(chain, "a", 3)].sort()).toEqual(["a", "b", "c", "d"]);
  });

  it("follows edges in BOTH directions (what it imports and what imports it)", () => {
    expect([...neighborhoodIds(chain, "c", 1)].sort()).toEqual(["b", "c", "d"]);
  });

  it("is capped at 3 hops no matter what is asked for", () => {
    expect([...neighborhoodIds(chain, "a", 99)].sort()).toEqual(["a", "b", "c", "d"]);
  });

  it("terminates on cycles and does not duplicate nodes", () => {
    const cyc = [e("a", "b"), e("b", "c"), e("c", "a")];
    expect([...neighborhoodIds(cyc, "a", 3)].sort()).toEqual(["a", "b", "c"]);
  });

  it("includes edges' other ends for a hub (fan-in and fan-out together)", () => {
    const hub = [e("x", "hub"), e("y", "hub"), e("hub", "z")];
    expect([...neighborhoodIds(hub, "hub", 1)].sort()).toEqual(["hub", "x", "y", "z"]);
  });

  it("a file with no edges is only itself; an unknown id is harmless", () => {
    expect([...neighborhoodIds(chain, "lonely", 2)]).toEqual(["lonely"]);
  });

  it("does not leak into a separate component", () => {
    const two = [e("a", "b"), e("x", "y")];
    expect([...neighborhoodIds(two, "a", 3)].sort()).toEqual(["a", "b"]);
  });
});

describe("pickFocusStart", () => {
  it("returns null for an empty project", () => {
    expect(pickFocusStart([])).toBeNull();
  });

  it("prefers an entry-like file: nothing imports it, it imports the most", () => {
    const nodes = [n("util", 9, 0), n("entry-small", 0, 2), n("entry-big", 0, 7), n("mid", 3, 3)];
    expect(pickFocusStart(nodes)).toBe("entry-big");
  });

  it("falls back to the best-connected file when everything is imported by something", () => {
    const nodes = [n("a", 1, 1), n("b", 4, 3), n("c", 2, 0)];
    expect(pickFocusStart(nodes)).toBe("b");
  });

  it("ignores files with no imports as entry candidates", () => {
    const nodes = [n("isolated", 0, 0), n("real", 0, 1)];
    expect(pickFocusStart(nodes)).toBe("real");
  });

  it("never starts on a test file when the project has anything else", () => {
    const nodes = [
      { ...n("tests/test_login.py", 0, 9), architectureType: "Test" },
      { ...n("src/main.py", 0, 3), architectureType: "Util" },
    ];
    expect(pickFocusStart(nodes)).toBe("src/main.py");
  });

  it("falls back to test files when they are all the project has", () => {
    const nodes = [{ ...n("test_a.py", 0, 2), architectureType: "Test" }];
    expect(pickFocusStart(nodes)).toBe("test_a.py");
  });

  it("is deterministic on ties (path order)", () => {
    const nodes = [n("b.js", 0, 2), n("a.js", 0, 2)];
    expect(pickFocusStart(nodes)).toBe("a.js");
    expect(pickFocusStart([...nodes].reverse())).toBe("a.js");
  });
});

it("the large-graph threshold is a sane positive number", () => {
  expect(LARGE_GRAPH_THRESHOLD).toBeGreaterThan(20);
});
