import { Component, PanelTop, Route, Cog, Webhook, Database, Settings2 } from "lucide-react";
import { colorForCategory } from "../utils/nodeColor";

/**
 * A small, real-looking dependency map for the home page: the product's own
 * output, drawn as the first thing you see. It plays once on load (nodes
 * appear left to right, edges draw in) - the page's single orchestrated
 * moment - and sits still after that. Purely decorative, so hidden from
 * assistive tech.
 */
const W = 148;
const H = 46;

const NODES = [
  { id: "main", name: "main.jsx", cat: "Route", Icon: Route, x: 0, y: 138, col: 0 },
  { id: "app", name: "App.jsx", cat: "Component", Icon: Component, x: 172, y: 138, col: 1 },
  { id: "dash", name: "Dashboard.jsx", cat: "Page", Icon: PanelTop, x: 344, y: 138, col: 2 },
  { id: "ctl", name: "Controls.jsx", cat: "Component", Icon: Component, x: 516, y: 14, col: 3 },
  { id: "lap", name: "LapChart.jsx", cat: "Component", Icon: Component, x: 516, y: 76, col: 3 },
  { id: "hook", name: "usePlayer.js", cat: "Hook", Icon: Webhook, x: 516, y: 138, col: 3 },
  { id: "api", name: "api.js", cat: "Service", Icon: Cog, x: 516, y: 200, col: 3 },
  { id: "cfg", name: "config.js", cat: "Config", Icon: Settings2, x: 516, y: 262, col: 3 },
  { id: "auth", name: "auth.js", cat: "Service", Icon: Cog, x: 172, y: 330, col: 1, cycle: true },
  { id: "sess", name: "session.js", cat: "Model", Icon: Database, x: 344, y: 330, col: 2, cycle: true },
];

const EDGES = [
  ["main", "app"], ["app", "dash"],
  ["dash", "ctl"], ["dash", "lap"], ["dash", "hook"], ["dash", "api"], ["dash", "cfg"],
];

const byId = Object.fromEntries(NODES.map((n) => [n.id, n]));

function edgePath(a, b) {
  const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2;
  const dx = Math.max(24, (x2 - x1) / 2);
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
}

export default function HeroGraph() {
  const auth = byId.auth, sess = byId.sess;
  return (
    <svg viewBox="0 0 674 420" className="w-full h-auto" aria-hidden="true" focusable="false">
      <g fill="none" strokeWidth="1.6" strokeLinecap="round">
        {EDGES.map(([from, to]) => {
          const a = byId[from], b = byId[to];
          return (
            <path
              key={`${from}-${to}`}
              d={edgePath(a, b)}
              className="hero-edge"
              style={{ stroke: colorForCategory(a.cat), opacity: 0.6, "--d": `${0.35 + a.col * 0.2}s` }}
            />
          );
        })}
        {/* the cycle: one edge each way, in the danger colour */}
        <path d={edgePath(auth, sess)} className="hero-edge" style={{ stroke: "var(--danger)", "--d": "1.1s" }} />
        <path
          d={`M ${sess.x + W / 2} ${sess.y + H} C ${sess.x + W / 2} ${sess.y + H + 30}, ${auth.x + W / 2} ${sess.y + H + 30}, ${auth.x + W / 2} ${auth.y + H}`}
          className="hero-edge"
          style={{ stroke: "var(--danger)", strokeDasharray: "5 4", "--d": "1.25s" }}
        />
      </g>

      <g className="hero-node" style={{ "--d": "1.35s" }}>
        <rect x={auth.x} y={auth.y - 30} width={W} height={22} rx={11} style={{ fill: "color-mix(in srgb, var(--danger) 14%, var(--surface))", stroke: "color-mix(in srgb, var(--danger) 45%, transparent)" }} />
        <text x={auth.x + W / 2} y={auth.y - 15} textAnchor="middle" fontSize="11" fontWeight="600" style={{ fill: "var(--fg)" }}>
          Circular dependency
        </text>
      </g>

      {NODES.map((n) => {
        const color = colorForCategory(n.cat);
        return (
          <g key={n.id} className="hero-node" style={{ "--d": `${n.col * 0.2 + (n.y > 300 ? 0.9 : 0)}s`, filter: "drop-shadow(0 6px 12px rgb(0 0 0 / 0.07))" }}>
            <rect x={n.x} y={n.y} width={W} height={H} rx={12} style={{ fill: "var(--surface)", stroke: "var(--line-strong)" }} />
            <rect x={n.x + 8} y={n.y + 8} width={30} height={30} rx={9} style={{ fill: `color-mix(in srgb, ${color} 20%, transparent)` }} />
            <n.Icon x={n.x + 15} y={n.y + 15} size={16} strokeWidth={2} style={{ color: `color-mix(in srgb, ${color} 72%, var(--fg))` }} />
            <text x={n.x + 46} y={n.y + 28} fontSize="12.5" fontWeight="600" style={{ fill: "var(--fg)" }}>{n.name}</text>
            {n.cycle && <circle cx={n.x + W - 2} cy={n.y + 2} r={5} style={{ fill: "var(--danger)", stroke: "var(--surface)" }} strokeWidth="2" />}
          </g>
        );
      })}
    </svg>
  );
}
