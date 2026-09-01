import { useMemo, useState } from "react";
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
    <div className="h-full flex flex-col">
      <div className="p-2 border-b border-ink-700">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search files"
          className="w-full bg-ink-800 border border-ink-600 rounded-sm px-2.5 py-1.5 text-[12px] font-mono text-parchment-100 placeholder:text-parchment-600 focus:outline-none focus:border-brass-500"
        />
      </div>

      <div className="flex-1 overflow-y-auto py-1.5">
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
    return <p className="px-3 py-2 text-[12px] text-parchment-500">No files match.</p>;
  }
  return (
    <ul>
      {matches.map((node) => (
        <FileRow key={node.id} node={node} depth={0} selectedNodeId={selectedNodeId} onSelect={onSelect} />
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
          className="w-full flex items-center gap-1.5 px-3 py-1 text-[12px] text-parchment-300 hover:text-parchment-100"
          style={{ paddingLeft: 12 + depth * 12 }}
        >
          <span className="w-3 inline-block text-parchment-500">{open ? "▾" : "▸"}</span>
          {folder.name}
        </button>
      )}
      {open && (
        <div>
          {entries.map((entry) =>
            entry.type === "folder" ? (
              <Folder
                key={entry.name}
                folder={entry}
                depth={depth + 1}
                selectedNodeId={selectedNodeId}
                onSelect={onSelect}
              />
            ) : (
              <FileRow
                key={entry.id}
                node={entry.node}
                depth={depth + 1}
                selectedNodeId={selectedNodeId}
                onSelect={onSelect}
              />
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
      className={`w-full flex items-center gap-2 px-3 py-1 text-[12px] font-mono truncate text-left
        ${isSelected ? "bg-ink-700 text-parchment-100" : "text-parchment-200 hover:bg-ink-800 hover:text-parchment-100"}`}
      style={{ paddingLeft: 12 + depth * 12 }}
    >
      <span
        className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0"
        style={{ background: color }}
      />
      <span className="truncate">{node.name}</span>
    </button>
  );
}
