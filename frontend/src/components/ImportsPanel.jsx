/**
 * Shows exactly what the selected file imports (and what symbols it pulls
 * from each dependency), plus who imports it back and what they use.
 *
 * This is deliberately NOT rendered on the graph canvas itself - a graph
 * with per-edge symbol labels on every line would be unreadable clutter.
 * The graph stays clean; this panel is where the detail lives.
 */
export default function ImportsPanel({ node, edges }) {
  if (!node) return null;

  const outgoing = edges.filter((e) => e.source === node.id);
  const incoming = edges.filter((e) => e.target === node.id);

  if (outgoing.length === 0 && incoming.length === 0) return null;

  return (
    <div className="px-4 py-4 border-t border-ink-700">
      <Section title="Imports" edges={outgoing} field="target" emptyLabel="No local imports." />
      <div className="mt-4">
        <Section
          title="Imported by"
          edges={incoming}
          field="source"
          emptyLabel="Nothing imports this file."
        />
      </div>
    </div>
  );
}

function Section({ title, edges, field, emptyLabel }) {
  return (
    <div>
      <h3 className="font-display text-[12px] font-medium text-parchment-300">{title}</h3>
      {edges.length === 0 ? (
        <p className="mt-2 text-[12px] text-parchment-500">{emptyLabel}</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {edges.map((edge) => (
            <EdgeRow key={`${edge.source}->${edge.target}`} edge={edge} field={field} />
          ))}
        </ul>
      )}
    </div>
  );
}

function EdgeRow({ edge, field }) {
  const otherFile = edge[field];
  return (
    <li>
      <div className="font-mono text-[12px] text-parchment-200 truncate">
        {basename(otherFile)}
      </div>
      {edge.symbols?.length > 0 && (
        <div className="mt-0.5 text-[11px] text-parchment-500 truncate">
          {edge.symbols.join(", ")}
        </div>
      )}
    </li>
  );
}

function basename(path) {
  return path.includes("/") ? path.slice(path.lastIndexOf("/") + 1) : path;
}
