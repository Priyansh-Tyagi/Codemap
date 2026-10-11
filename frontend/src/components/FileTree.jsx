import { useMemo, useState } from "react";
import { ChevronRight, Search } from "lucide-react";
import { buildFileTree, sortedEntries } from "../utils/buildFileTree";
import { colorForCategory } from "../utils/nodeColor";

export default function FileTree({ nodes, selectedNodeId, onSelect }) {
  const [query, setQuery] = useState("");
  const tree = useMemo(() => buildFileTree(nodes), [nodes]);

  const matches = useMemo(() => {
    if (!query.trim()) return null;
    const q = query.trim().toLowerCase();
    return nodes
      .filter((n) => n.filePath.toLowerCase().includes(q))
      .sort((a, b) => a.filePath.localeCompare(b.filePath));
  }, [nodes, query]);

  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="p-3 pb-2">
        <label className="relative block">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" aria-hidden="true" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search files"
            aria-label="Search files"
            className="w-full bg-surface-2 border border-line rounded-lg pl-8 pr-2.5 py-1.5 text-[12.5px] text-fg placeholder:text-faint hover:border-line-strong focus:outline-none focus:border-fg transition-colors"
          />
        </label>
      </div>

      <div className="flex-1 overflow-y-auto px-1.5 pb-2">
        {matches ? (
          <SearchResults matches={matches} selectedNodeId={selectedNodeId} onSelect={onSelect} />
        ) : (
          <Folder folder={tree} depth={0} selectedNodeId={selectedNodeId} onSelect={onSelect} />
        )}
      </div>
    </div>
  );
}

function SearchResults({ matches, selectedNodeId, onSelect }) {
  if (matches.length === 0) {
    return <p className="px-3 py-2 text-[12px] text-muted">No files match.</p>;
  }
  return (
    <ul>
      {matches.map((node) => (
        <li key={node.id}>
          <FileRow node={node} depth={0} selectedNodeId={selectedNodeId} onSelect={onSelect} />
        </li>
      ))}
    </ul>
  );
}

function Folder({ folder, depth, selectedNodeId, onSelect }) {
  const [open, setOpen] = useState(true);
  const entries = sortedEntries(folder);

  return (
    <div>
      {folder.name && (
        <button
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="w-full flex items-center gap-1 py-1 pr-2 rounded-md text-[12.5px] font-medium text-fg-soft hover:bg-surface-2"
          style={{ paddingLeft: 6 + depth * 12 }}
        >
          <ChevronRight
            size={13}
            className={`text-faint transition-transform ${open ? "rotate-90" : ""}`}
            aria-hidden="true"
          />
          <span className="truncate">{folder.name}</span>
        </button>
      )}
      {open && (
        <div>
          {entries.map((entry) =>
            entry.type === "folder" ? (
              <Folder key={entry.name} folder={entry} depth={depth + 1} selectedNodeId={selectedNodeId} onSelect={onSelect} />
            ) : (
              <FileRow key={entry.id} node={entry.node} depth={depth + 1} selectedNodeId={selectedNodeId} onSelect={onSelect} />
            )
          )}
        </div>
      )}
    </div>
  );
}

function FileRow({ node, depth, selectedNodeId, onSelect }) {
  const isSelected = node.id === selectedNodeId;
  const color = colorForCategory(node.architectureType);

  return (
    <button
      onClick={() => onSelect(node)}
      aria-current={isSelected ? "true" : undefined}
      title={node.filePath}
      className={`w-full flex items-center gap-2 py-1 pr-2 rounded-md text-[12px] font-mono text-left
        ${isSelected ? "bg-surface-3 text-fg" : "text-fg-soft hover:bg-surface-2 hover:text-fg"}`}
      style={{ paddingLeft: 8 + depth * 12 }}
    >
      <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
      <span className="truncate">{node.name}</span>
    </button>
  );
}
