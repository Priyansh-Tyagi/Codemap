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

const GRID_GAP_X = 24;
const GRID_GAP_Y = 20;
const GRID_SEPARATION = 80; // space between the connected graph and the isolated-files grid

/**
 * Lays isolated files (no import edges to or from any other visible file) out
 * in a compact grid. Left to dagre, every one of them lands on rank 0 and they
 * stack into a single enormous column - on a real repo (Flask: 60+ isolated
 * files) that column dwarfs the actual dependency graph and pushes it
 * off-screen. A grid keeps them visible but out of the way.
 */
function layoutIsolatedGrid(isolatedNodes, originX, originY, targetWidth) {
  const cellW = NODE_WIDTH + GRID_GAP_X;
  const cellH = NODE_HEIGHT + GRID_GAP_Y;
  const count = isolatedNodes.length;
  const byWidth = Math.floor(targetWidth / cellW);
  const bySquare = Math.ceil(Math.sqrt(count * 1.5));
  const cols = Math.max(1, Math.min(count, Math.max(byWidth, bySquare)));

  const positions = new Map();
  isolatedNodes.forEach((node, i) => {
    positions.set(node.id, {
      x: originX + (i % cols) * cellW,
      y: originY + Math.floor(i / cols) * cellH,
    });
  });
  return positions;
}

/**
 * Computes {x, y} positions: connected files via dagre (ranked on forward
 * edges only), isolated files in a grid below. Returns which edges were held
 * back as feedback edges, so the caller can style/route those differently.
 */
export function layoutWithDagre(nodes, edges, direction = "LR") {
  const nodeIds = new Set(nodes.map((n) => n.id));
  const visibleEdges = edges.filter(
    (e) => e.source !== e.target && nodeIds.has(e.source) && nodeIds.has(e.target)
  );
  const connectedIds = new Set();
  for (const e of visibleEdges) {
    connectedIds.add(e.source);
    connectedIds.add(e.target);
  }
  const connectedNodes = nodes.filter((n) => connectedIds.has(n.id));
  const isolatedNodes = nodes.filter((n) => !connectedIds.has(n.id));

  const { forward, feedback } = splitFeedbackEdges(connectedNodes, visibleEdges);

  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: direction,
    nodesep: 40,
    ranksep: 90,
    marginx: 20,
    marginy: 20,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of connectedNodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of forward) {
    g.setEdge(edge.source, edge.target);
  }

  if (connectedNodes.length > 0) dagre.layout(g);

  const positions = new Map();
  let minX = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const node of connectedNodes) {
    const { x, y } = g.node(node.id);
    const pos = { x: x - NODE_WIDTH / 2, y: y - NODE_HEIGHT / 2 };
    positions.set(node.id, pos);
    minX = Math.min(minX, pos.x);
    maxX = Math.max(maxX, pos.x + NODE_WIDTH);
    maxY = Math.max(maxY, pos.y + NODE_HEIGHT);
  }

  if (isolatedNodes.length > 0) {
    const hasConnected = connectedNodes.length > 0;
    const grid = layoutIsolatedGrid(
      isolatedNodes,
      hasConnected ? minX : 0,
      hasConnected ? maxY + GRID_SEPARATION : 0,
      hasConnected ? maxX - minX : 0
    );
    for (const [id, pos] of grid) positions.set(id, pos);
  }

  const feedbackEdgeKeys = new Set(feedback.map((e) => `${e.source}->${e.target}`));

  return { positions, feedbackEdgeKeys };
}

export const NODE_DIMENSIONS = { width: NODE_WIDTH, height: NODE_HEIGHT };
