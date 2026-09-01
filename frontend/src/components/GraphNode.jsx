import { Handle, Position } from "reactflow";
import { colorForCategory, colorForRisk } from "../utils/nodeColor";

/**
 * Rounded-card node (not a plain rectangle, not an unlabeled circle):
 * a left accent bar carries the architecture-category color, the filename
 * is readable directly on the card, and risk/cycle are shown as small
 * layered indicators rather than replacing the category color - so you
 * never lose "what kind of file is this" just because it's also flagged.
 */
export default function GraphNode({ data }) {
  const { node, dimmed, selected } = data;
  const categoryColor = colorForCategory(node.architectureType);
  const riskColor = colorForRisk(node.riskLevel);

  return (
    <div
      className="transition-opacity duration-200"
      style={{ width: 190, opacity: dimmed ? 0.18 : 1 }}
    >
      <div
        className="relative rounded-md bg-ink-900 overflow-hidden flex items-stretch"
        style={{
          border: `1px solid ${selected ? categoryColor : "#232838"}`,
          boxShadow: selected ? `0 0 0 3px ${categoryColor}33` : "none",
        }}
      >
        <Handle type="target" position={Position.Left} style={handleStyle} />
        <Handle type="source" position={Position.Right} style={handleStyle} />

        <div className="w-1" style={{ background: categoryColor }} />

        <div className="flex-1 min-w-0 px-2.5 py-2">
          <div className="flex items-center gap-1.5">
            <span className="truncate font-display text-[12.5px] font-medium text-parchment-100">
              {node.name}
            </span>
            {node.inCycle && (
              <span
                title="Part of a circular dependency"
                className="flex-shrink-0 w-1.5 h-1.5 rounded-full"
                style={{ background: "#D1615C" }}
              />
            )}
          </div>

          <div className="mt-1 flex items-center gap-2 font-mono text-[10px] text-parchment-500">
            <span>{node.outDegree} deps</span>
            <span>{node.inDegree} used by</span>
          </div>
        </div>

        {riskColor && (node.riskLevel === "High" || node.riskLevel === "Critical") && (
          <div
            title={`${node.riskLevel} risk`}
            className="w-1 flex-shrink-0"
            style={{ background: riskColor }}
          />
        )}
      </div>
    </div>
  );
}

const handleStyle = {
  background: "transparent",
  border: "none",
  width: 1,
  height: 1,
};
