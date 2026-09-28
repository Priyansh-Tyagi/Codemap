import { describe, it, expect } from "vitest";
import { layoutWithDagre, NODE_DIMENSIONS } from "./dagreLayout";

const n = (id) => ({ id });
const e = (source, target) => ({ source, target });
const { width: W, height: H } = NODE_DIMENSIONS;

function boxes(positions) {
  return [...positions.entries()].map(([id, p]) => ({ id, x: p.x, y: p.y }));
}
function overlaps(a, b) {
  return a.x < b.x + W && b.x < a.x + W && a.y < b.y + H && b.y < a.y + H;
}
function bbox(positions) {
  const bs = boxes(positions);
  const xs = bs.map((b) => b.x), ys = bs.map((b) => b.y);
  return { w: Math.max(...xs) + W - Math.min(...xs), h: Math.max(...ys) + H - Math.min(...ys) };
}

describe("layoutWithDagre", () => {
  it("gives every node a position, including isolated ones", () => {
    const nodes = ["a", "b", "c", "lonely"].map(n);
    const { positions } = layoutWithDagre(nodes, [e("a", "b"), e("b", "c")]);
    expect([...positions.keys()].sort()).toEqual(["a", "b", "c", "lonely"]);
  });

  it("does not stack many isolated files into one tall column", () => {
    const connected = ["a", "b", "c"].map(n);
    const isolated = Array.from({ length: 70 }, (_, i) => n(`iso${i}`));
    const { positions } = layoutWithDagre([...connected, ...isolated], [e("a", "b"), e("b", "c")]);
    const { w, h } = bbox(positions);
    // 70 stacked nodes would be ~70 * (H+40) = 6700px tall and one node wide.
    expect(h).toBeLessThan(2000);
    expect(w).toBeGreaterThan(W * 3);
  });

  it("places isolated files below the connected graph, without overlapping anything", () => {
    const nodes = ["a", "b", "c", "x", "y", "z"].map(n);
    const { positions } = layoutWithDagre(nodes, [e("a", "b"), e("b", "c")]);
    const connectedBottom = Math.max(...["a", "b", "c"].map((id) => positions.get(id).y + H));
    for (const id of ["x", "y", "z"]) expect(positions.get(id).y).toBeGreaterThan(connectedBottom);

    const bs = boxes(positions);
    for (let i = 0; i < bs.length; i++)
      for (let j = i + 1; j < bs.length; j++) expect(overlaps(bs[i], bs[j])).toBe(false);
  });

  it("handles a graph with no edges at all", () => {
    const nodes = Array.from({ length: 10 }, (_, i) => n(`f${i}`));
    const { positions, feedbackEdgeKeys } = layoutWithDagre(nodes, []);
    expect(positions.size).toBe(10);
    expect(feedbackEdgeKeys.size).toBe(0);
  });

  it("handles an empty graph", () => {
    const { positions } = layoutWithDagre([], []);
    expect(positions.size).toBe(0);
  });

  it("still routes a cycle's closing edge as a feedback edge", () => {
    const nodes = ["a", "b", "c"].map(n);
    const { feedbackEdgeKeys } = layoutWithDagre(nodes, [e("a", "b"), e("b", "c"), e("c", "a")]);
    expect(feedbackEdgeKeys.size).toBe(1);
  });

  it("ignores edges whose endpoints were filtered out, and self-loops don't count as connections", () => {
    const nodes = ["a", "b"].map(n);
    const { positions } = layoutWithDagre(nodes, [e("a", "gone"), e("b", "b")]);
    expect(positions.size).toBe(2);
    expect(Number.isFinite(positions.get("a").x)).toBe(true);
  });
});
