/**
 * Pure logic for "focus mode": show only the neighborhood of one file instead
 * of the whole graph. Kept component-free (same pattern as filterNodes.js) so
 * it is directly testable.
 *
 * Why this exists: a 150-file graph laid out all at once is an unreadable
 * column of tiny boxes. Dimming nodes doesn't fix that (they still take up
 * layout space); removing everything except what's near the file you care
 * about does.
 */

/** Above this many files the project opens in focus mode instead of the full graph. */
export const LARGE_GRAPH_THRESHOLD = 60;

export const MAX_HOPS = 3;

/**
 * Ids of every node within `hops` import-steps of `rootId`, in EITHER
 * direction (what it imports, what imports it, and transitively), including
 * the root itself. Breadth-first, so cycles can't loop forever.
 */
export function neighborhoodIds(edges, rootId, hops) {
  const reached = new Set([rootId]);
  const limit = Math.max(0, Math.min(hops, MAX_HOPS));
  if (limit === 0) return reached;

  const adjacent = new Map();
  const link = (a, b) => {
    if (!adjacent.has(a)) adjacent.set(a, []);
    adjacent.get(a).push(b);
  };
  for (const e of edges) {
    link(e.source, e.target);
    link(e.target, e.source);
  }

  let frontier = [rootId];
  for (let depth = 0; depth < limit && frontier.length > 0; depth++) {
    const next = [];
    for (const id of frontier) {
      for (const neighbor of adjacent.get(id) ?? []) {
        if (!reached.has(neighbor)) {
          reached.add(neighbor);
          next.push(neighbor);
        }
      }
    }
    frontier = next;
  }
  return reached;
}

/**
 * Fallback starting file when the guided tour's entry point isn't available:
 * prefer something entry-like (imported by nothing, imports a lot), then
 * fall back to the best-connected file. Test files are skipped (unless the
 * project is nothing BUT tests): nothing imports a test, so by degree alone
 * they always look like entry points - found on a real repo, where the
 * heuristic picked a pytest file over the app's actual entry.
 * Deterministic: ties break on path.
 */
export function pickFocusStart(nodes) {
  if (nodes.length === 0) return null;

  const nonTests = nodes.filter((n) => n.architectureType !== "Test");
  const pool = nonTests.length > 0 ? nonTests : nodes;

  const byConnectivity = (a, b) =>
    b.outDegree - a.outDegree ||
    b.inDegree + b.outDegree - (a.inDegree + a.outDegree) ||
    a.id.localeCompare(b.id);

  const entryLike = pool.filter((n) => n.inDegree === 0 && n.outDegree > 0).sort(byConnectivity);
  if (entryLike.length > 0) return entryLike[0].id;

  return [...pool].sort(
    (a, b) => b.inDegree + b.outDegree - (a.inDegree + a.outDegree) || a.id.localeCompare(b.id)
  )[0].id;
}
