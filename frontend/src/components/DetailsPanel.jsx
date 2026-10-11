import { colorForCategory, colorForRisk } from "../utils/nodeColor";
import { iconForCategory } from "../utils/categoryIcon";

export default function DetailsPanel({ node, stats }) {
  return (
    <div>
      {node ? <FileSpec node={node} /> : <EmptySelection />}
      {stats && (
        <div className="border-t border-line">
          <ProjectStats stats={stats} />
        </div>
      )}
    </div>
  );
}

function EmptySelection() {
  return (
    <div className="px-4 py-5 text-[13px] text-muted leading-relaxed">
      Select a file in the graph to see its dependencies and metrics here.
    </div>
  );
}

function FileSpec({ node }) {
  const dir = node.filePath.includes("/") ? node.filePath.slice(0, node.filePath.lastIndexOf("/")) : null;
  const color = colorForCategory(node.architectureType);
  const Icon = iconForCategory(node.architectureType);
  const riskColor = colorForRisk(node.riskLevel);

  return (
    <div className="px-4 py-4">
      <div className="flex items-center gap-3">
        <span
          className="grid place-items-center w-10 h-10 rounded-xl flex-shrink-0"
          style={{
            background: `color-mix(in srgb, ${color} 20%, transparent)`,
            color: `color-mix(in srgb, ${color} 72%, var(--fg))`,
          }}
        >
          <Icon size={19} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold text-fg truncate leading-tight">{node.name}</h2>
          {dir && <div className="mt-0.5 font-mono text-[11px] text-faint truncate" title={dir}>{dir}</div>}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <Badge color={color} label={node.architectureType} />
        {node.riskLevel && node.riskLevel !== "Low" && <Badge color={riskColor} label={`${node.riskLevel} risk`} />}
        {node.inCycle && <Badge color="var(--danger)" label="Circular dependency" />}
      </div>

      <div className="mt-4 grid grid-cols-3 divide-x divide-line rounded-xl border border-line">
        <Metric label="Imports" value={node.outDegree} />
        <Metric label="Imported by" value={node.inDegree} />
        <Metric label="Depth" value={node.dependencyDepth} />
      </div>

      {node.riskScore !== null && (
        <div className="mt-4">
          <div className="flex items-baseline justify-between text-[12px]">
            <span className="text-muted">Risk score</span>
            <span className="font-medium text-fg tabular-nums">{node.riskScore} / 100</span>
          </div>
          <div className="mt-1.5 h-1.5 rounded-full bg-surface-3 overflow-hidden" role="presentation">
            <div
              className="h-full rounded-full"
              style={{ width: `${Math.min(100, Math.max(2, node.riskScore))}%`, background: riskColor ?? "var(--muted)" }}
            />
          </div>
        </div>
      )}

      <dl className="mt-3 divide-y divide-line">
        <Row label="Language" value={node.language === "python" ? "Python" : "JavaScript/TS"} />
        <Row label="Lines of code" value={node.linesOfCode} />
        <Row label="Centrality" value={node.degreeCentrality.toFixed(2)} />
      </dl>

      {node.riskReasons?.length > 0 && (
        <div className="mt-3">
          <p className="text-[12px] font-medium text-fg">Why this score</p>
          <ul className="mt-1.5 space-y-1">
            {node.riskReasons.map((reason) => (
              <li key={reason} className="text-[12px] text-muted leading-snug">{reason}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="px-3 py-2.5 text-center">
      <div className="text-[18px] font-semibold text-fg tabular-nums leading-none">{value}</div>
      <div className="mt-1 text-[11px] text-muted">{label}</div>
    </div>
  );
}

function Badge({ color, label }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full pl-1.5 pr-2 py-0.5 text-[11px] font-medium text-fg"
      style={{
        background: `color-mix(in srgb, ${color} 14%, transparent)`,
        border: `1px solid color-mix(in srgb, ${color} 45%, transparent)`,
      }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

function Row({ label, value, alert = false }) {
  return (
    <div className="flex items-baseline justify-between py-2 text-[12.5px]">
      <dt className="text-muted">{label}</dt>
      <dd className={`font-medium tabular-nums ${alert ? "text-danger" : "text-fg"}`}>{value}</dd>
    </div>
  );
}

function ProjectStats({ stats }) {
  return (
    <div className="px-4 py-4">
      <h3 className="text-[12px] font-semibold text-fg">Project</h3>
      <dl className="mt-1.5 divide-y divide-line">
        <Row label="Files" value={stats.fileCount} />
        <Row label="Dependencies" value={stats.edgeCount} />
        <Row label="Circular cycles" value={stats.cyclesTruncated ? `${stats.cycleCount}+` : stats.cycleCount} alert={stats.cycleCount > 0} />
        {stats.cyclicComponentCount > 0 && <Row label="Tangled clusters" value={stats.cyclicComponentCount} />}
        <Row label="High-risk files" value={stats.highRiskCount} alert={stats.highRiskCount > 0} />
        <Row label="Avg. dependencies" value={stats.avgDependencies} />
      </dl>
    </div>
  );
}
