import dagre from "dagre";

const NODE_WIDTH = 190;
const NODE_HEIGHT = 56;

/**
 * Splits edges into "forward" (safe to feed into a ranked layout) and
 * "feedback" (the edge that closes a cycle) using a standard DFS coloring
 * technique: an edge to a node that's currently on the recursion stack
 * (GRAY) is a back-edge - the thing making the graph cyclic. Removing just
 * those edges leaves an acyclic graph dagre can actually rank.
 *
 * Why this matters: dagre computes left-to-right RANKS, which requires a
 * consistent "before/after" ordering. A cycle has no consistent ordering
 * by definition (A before B before C before A is a contradiction), so
 * feeding dagre a raw cycle collapses every node in it onto one rank and
 * sends the closing edge on a long, ugly detour to route around them -
 * exactly what showed up in testing. Laying out on the forward edges only,
 * then drawing feedback edges as a distinct curved "return" line, is the
 * standard way graph-layout tools handle this.
 */
function splitFeedbackEdges(nodes, edges) {
  const adjacency = new Map(nodes.map((n) => [n.id, []]));
  for (const edge of edges) {
    if (adjacency.has(edge.source)) adjacency.get(edge.source).push(edge);
  }

  const WHITE = 0, GRAY = 1, BLACK = 2;
  const color = new Map(nodes.map((n) => [n.id, WHITE]));
  const forward = [];
  const feedback = [];

  function visit(nodeId) {
    color.set(nodeId, GRAY);
    for (const edge of adjacency.get(nodeId) || []) {
      const targetColor = color.get(edge.target);
      if (targetColor === GRAY) {
        feedback.push(edge); // back-edge: this is what makes it a cycle
      } else {
        forward.push(edge);
        if (targetColor === WHITE) visit(edge.target);
      }
    }
    color.set(nodeId, BLACK);
  }

  for (const node of nodes) {
    if (color.get(node.id) === WHITE) visit(node.id);
  }

  return { forward, feedback };
}

/**
 * Computes {x, y} positions via dagre (ranked on forward edges only) and
 * returns which edges were held back as feedback edges, so the caller can
 * style/route those differently.
 */
export function layoutWithDagre(nodes, edges, direction = "LR") {
  const { forward, feedback } = splitFeedbackEdges(nodes, edges);

  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: direction,
    nodesep: 40,
    ranksep: 90,
    marginx: 20,
    marginy: 20,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of forward) {
    if (g.hasNode(edge.source) && g.hasNode(edge.target)) {
      g.setEdge(edge.source, edge.target);
    }
  }

  dagre.layout(g);

  const positions = new Map();
  for (const node of nodes) {
    const { x, y } = g.node(node.id);
    positions.set(node.id, { x: x - NODE_WIDTH / 2, y: y - NODE_HEIGHT / 2 });
  }

  const feedbackEdgeKeys = new Set(feedback.map((e) => `${e.source}->${e.target}`));

  return { positions, feedbackEdgeKeys };
}

export const NODE_DIMENSIONS = { width: NODE_WIDTH, height: NODE_HEIGHT };
