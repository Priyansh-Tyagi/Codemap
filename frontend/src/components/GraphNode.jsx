import { Handle, Position } from "reactflow";
import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { colorForCategory, colorForRisk } from "../utils/nodeColor";
import { iconForCategory } from "../utils/categoryIcon";

/**
 * A node card: a glyph chip carries the architecture category (shape AND
 * colour), the filename is the headline, and the two numbers say how many
 * files it imports and how many import it. Cycle and risk are small flags on
 * the card's corner, layered on top so a flagged file never loses its
 * category. Fixed 190x56 to match the layout engine (utils/dagreLayout.js).
 */
export default function GraphNode({ data }) {
  const { node, dimmed, selected } = data;
  const color = colorForCategory(node.architectureType);
  const Icon = iconForCategory(node.architectureType);
  const riskColor = colorForRisk(node.riskLevel);
  const flagged = node.riskLevel === "High" || node.riskLevel === "Critical";

  return (
    <div className="transition-opacity duration-200" style={{ width: 190, height: 56, opacity: dimmed ? 0.2 : 1 }}>
      <div
        className="relative h-full flex items-center gap-2.5 px-2.5 rounded-xl bg-surface border transition-shadow"
        style={{
          borderColor: selected ? "var(--fg)" : "var(--line-strong)",
          boxShadow: selected
            ? "0 0 0 4px color-mix(in srgb, var(--fg) 12%, transparent), var(--soft)"
            : "0 1px 2px rgb(0 0 0 / 0.05)",
        }}
      >
        <Handle type="target" position={Position.Left} style={portStyle} />
        <Handle type="source" position={Position.Right} style={portStyle} />

        <span
          className="grid place-items-center w-8 h-8 rounded-lg flex-shrink-0"
          style={{
            background: `color-mix(in srgb, ${color} 20%, transparent)`,
            color: `color-mix(in srgb, ${color} 72%, var(--fg))`,
          }}
        >
          <Icon size={16} strokeWidth={2} aria-hidden="true" />
        </span>

        <div className="min-w-0 flex-1">
          <div className="truncate text-[12.5px] font-semibold text-fg leading-tight">{node.name}</div>
          <div className="mt-1 flex items-center gap-2.5 text-[10.5px] text-muted tabular-nums">
            <span className="inline-flex items-center gap-0.5" title={`Imports ${node.outDegree} files`}>
              <ArrowUpRight size={11} aria-hidden="true" />
              {node.outDegree}
              <span className="sr-only"> imports</span>
            </span>
            <span className="inline-flex items-center gap-0.5" title={`Imported by ${node.inDegree} files`}>
              <ArrowDownLeft size={11} aria-hidden="true" />
              {node.inDegree}
              <span className="sr-only"> imported by</span>
            </span>
          </div>
        </div>

        {node.inCycle && (
          <span
            title="Part of a circular dependency"
            className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-danger ring-2 ring-surface"
          />
        )}
        {flagged && (
          <span
            title={`${node.riskLevel} risk`}
            className="absolute -top-1 right-4 w-3 h-3 rounded-full ring-2 ring-surface"
            style={{ background: riskColor }}
          />
        )}
      </div>
    </div>
  );
}

// Visible ports, like a flow builder: small rings sitting on the card edge.
const portStyle = {
  width: 8,
  height: 8,
  background: "var(--surface)",
  border: "1.5px solid var(--line-strong)",
};
