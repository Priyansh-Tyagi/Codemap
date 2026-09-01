import { colorForCategory, colorForRisk } from "../utils/nodeColor";

export default function DetailsPanel({ node, stats }) {
  return (
    <div>
      {node ? <FileSpec node={node} /> : <EmptySelection />}
      {stats && (
        <div className="border-t border-ink-700">
          <ProjectStats stats={stats} />
        </div>
      )}
    </div>
  );
}

function EmptySelection() {
  return (
    <div className="px-4 py-5 text-[13px] text-parchment-400 leading-relaxed">
      Select a file in the graph to see its dependencies and metrics here.
    </div>
  );
}

function FileSpec({ node }) {
  const dir = node.filePath.includes("/")
    ? node.filePath.slice(0, node.filePath.lastIndexOf("/"))
    : null;
  const categoryColor = colorForCategory(node.architectureType);
  const riskColor = colorForRisk(node.riskLevel);

  return (
    <div className="px-4 py-4">
      {dir && (
        <div className="font-mono text-[11px] text-parchment-500 truncate">{dir}</div>
      )}
      <h2 className="font-display text-[15px] font-medium text-parchment-100 truncate">
        {node.name}
      </h2>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Badge color={categoryColor} label={node.architectureType} />
        {node.riskLevel && node.riskLevel !== "Low" && (
          <Badge color={riskColor} label={`${node.riskLevel} risk`} />
        )}
        {node.inCycle && <Badge color="#D1615C" label="Circular dependency" />}
      </div>

      <dl className="mt-4 divide-y divide-ink-700 border-y border-ink-700">
        <Row label="Lines of code" value={node.linesOfCode} />
        <Row label="Depends on" value={node.outDegree} />
        <Row label="Depended on by" value={node.inDegree} />
        <Row label="Dependency depth" value={node.dependencyDepth} />
        <Row label="Centrality" value={node.degreeCentrality.toFixed(2)} />
        {node.riskScore !== null && <Row label="Risk score" value={`${node.riskScore} / 100`} />}
      </dl>

      {node.riskReasons?.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] text-parchment-500">Why this score</p>
          <ul className="mt-1 space-y-0.5">
            {node.riskReasons.map((reason) => (
              <li key={reason} className="text-[12px] text-parchment-300">
                {reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Badge({ color, label }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[10.5px] font-mono"
      style={{ background: `${color}22`, color, border: `1px solid ${color}55` }}
    >
      {label}
    </span>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-baseline justify-between py-1.5 text-[13px]">
      <dt className="text-parchment-400">{label}</dt>
      <dd className="font-mono text-parchment-100">{value}</dd>
    </div>
  );
}

function ProjectStats({ stats }) {
  return (
    <div className="px-4 py-4">
      <h3 className="font-display text-[12px] font-medium text-parchment-300">
        Project
      </h3>
      <dl className="mt-2 divide-y divide-ink-700 border-y border-ink-700">
        <Row label="Files" value={stats.fileCount} />
        <Row label="Dependencies" value={stats.edgeCount} />
        <Row label="Circular cycles" value={stats.cycleCount} />
        <Row label="High-risk files" value={stats.highRiskCount} />
        <Row label="Avg. dependencies" value={stats.avgDependencies} />
      </dl>
    </div>
  );
}
