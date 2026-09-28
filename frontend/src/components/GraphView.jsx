import { forwardRef, useImperativeHandle, useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  useReactFlow,
  MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";
import GraphNode from "./GraphNode";
import { colorForCategory, CYCLE_COLOR } from "../utils/nodeColor";
import { layoutWithDagre } from "../utils/dagreLayout";

const nodeTypes = { codeNode: GraphNode };

/** Direct neighbors (either direction) of a node, given the full edge list. */
function connectedNodeIds(edges, nodeId) {
  const connected = new Set([nodeId]);
  for (const e of edges) {
    if (e.source === nodeId) connected.add(e.target);
    if (e.target === nodeId) connected.add(e.source);
  }
  return connected;
}

function GraphViewInner({ nodes, edges, onNodeClick, selectedNodeId }, ref) {
  const instance = useReactFlow();

  useImperativeHandle(ref, () => ({
    focusNode(nodeId) {
      const target = instance.getNodes().find((n) => n.id === nodeId);
      if (target) {
        instance.fitView({ nodes: [target], duration: 500, padding: 3, maxZoom: 1.1 });
      }
    },
  }));

  const { positions, feedbackEdgeKeys } = useMemo(
    () => layoutWithDagre(nodes, edges, "LR"),
    [nodes, edges]
  );

  const highlight = useMemo(
    () => (selectedNodeId ? connectedNodeIds(edges, selectedNodeId) : null),
    [edges, selectedNodeId]
  );

  const nodeById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const flowNodes = useMemo(
    () =>
      nodes.map((node) => ({
        id: node.id,
        type: "codeNode",
        position: positions.get(node.id) ?? { x: 0, y: 0 },
        data: {
          node,
          selected: node.id === selectedNodeId,
          dimmed: highlight ? !highlight.has(node.id) : false,
        },
      })),
    [nodes, positions, selectedNodeId, highlight]
  );

  const flowEdges = useMemo(
    () =>
      edges.map((edge, i) => {
        const sourceNode = nodeById.get(edge.source);
        const isCycleEdge = sourceNode?.inCycle && nodeById.get(edge.target)?.inCycle;
        const isFeedbackEdge = feedbackEdgeKeys.has(`${edge.source}->${edge.target}`);
        const color = isCycleEdge ? CYCLE_COLOR : colorForCategory(sourceNode?.architectureType);
        const connected =
          !highlight || (highlight.has(edge.source) && highlight.has(edge.target));
        return {
          id: `e${i}-${edge.source}-${edge.target}`,
          source: edge.source,
          target: edge.target,
          // Feedback edges (the ones that close a cycle) get a smooth curved
          // "return" line instead of the orthogonal step router - stepped
          // routing has nowhere sensible to go for a same-rank back-edge
          // and ends up overshooting the nodes, which is what showed up
          // in testing. A bezier arcs cleanly around instead.
          type: isFeedbackEdge ? "default" : "smoothstep",
          markerEnd: { type: MarkerType.ArrowClosed, color, width: 14, height: 14 },
          style: {
            stroke: color,
            strokeWidth: connected && highlight ? 2 : 1.25,
            strokeDasharray: isFeedbackEdge ? "4 3" : undefined,
            // quiet ambient state (nothing selected) so the graph doesn't
            // read as a tangle at rest; edges brighten on selection instead
            opacity: highlight ? (connected ? 0.9 : 0.06) : 0.35,
            transition: "opacity 200ms, stroke-width 200ms",
          },
        };
      }),
    [edges, nodeById, highlight, feedbackEdgeKeys]
  );

  return (
    <ReactFlow
      nodes={flowNodes}
      edges={flowEdges}
      nodeTypes={nodeTypes}
      onNodeClick={(_, node) => onNodeClick?.(node.data.node)}
      onPaneClick={() => onNodeClick?.(null)}
      fitView
      minZoom={0.05}
      proOptions={{ hideAttribution: true }}
    >
      <Background color="#161a24" gap={28} size={1} />
      <Controls className="[&_button]:bg-ink-800 [&_button]:border-ink-600 [&_button]:fill-parchment-300" />
      <MiniMap
        nodeColor={(n) =>
          n.data?.node?.inCycle ? CYCLE_COLOR : colorForCategory(n.data?.node?.architectureType)
        }
        nodeStrokeWidth={0}
        maskColor="rgba(11, 14, 20, 0.78)"
        style={{ background: "#12161f", border: "1px solid #232838" }}
      />
    </ReactFlow>
  );
}

const ForwardedGraphViewInner = forwardRef(GraphViewInner);

/** Public component: wraps the inner view in a ReactFlowProvider so useReactFlow works. */
const GraphView = forwardRef((props, ref) => (
  <div className="h-full w-full bg-ink-950">
    <ReactFlowProvider>
      <ForwardedGraphViewInner {...props} ref={ref} />
    </ReactFlowProvider>
  </div>
));

export default GraphView;
