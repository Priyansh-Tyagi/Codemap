import { useMemo } from "react";
import { colorForCategory } from "../utils/nodeColor";
import { availableCategories, availableFolders, hasActiveFilters } from "../utils/filterNodes";

export default function FilterPanel({ nodes, filters, onChange, visibleCount, onClear }) {
  const categories = useMemo(() => availableCategories(nodes), [nodes]);
  const folders = useMemo(() => availableFolders(nodes), [nodes]);
  const active = hasActiveFilters(filters);

  function toggleCategory(cat) {
    const next = new Set(filters.categories);
    if (next.has(cat)) next.delete(cat);
    else next.add(cat);
    onChange({ ...filters, categories: next });
  }

  return (
    <div className="p-3 border-b border-ink-700">
      <div className="flex items-center justify-between">
        <h3 className="font-display text-[11px] font-medium text-parchment-400">Filter</h3>
        {active && (
          <button
            onClick={onClear}
            className="text-[10px] text-brass-400 hover:text-brass-300"
          >
            Clear
          </button>
        )}
      </div>

      <div className="mt-2 flex flex-wrap gap-1">
        {categories.map((cat) => {
          const isActive = filters.categories.has(cat);
          const color = colorForCategory(cat);
          return (
            <button
              key={cat}
              type="button"
              onClick={() => toggleCategory(cat)}
              className="text-[10px] font-mono px-1.5 py-0.5 rounded-sm border transition-colors"
              style={{
                borderColor: isActive ? color : "#232838",
                color: isActive ? color : "#7c8397",
                background: isActive ? `${color}22` : "transparent",
              }}
            >
              {cat}
            </button>
          );
        })}
      </div>

      <div className="mt-2 flex gap-2">
        <select
          value={filters.minRisk ?? ""}
          onChange={(e) => onChange({ ...filters, minRisk: e.target.value || null })}
          className="flex-1 min-w-0 bg-ink-800 border border-ink-600 rounded-sm px-1.5 py-1 text-[10px] font-mono text-parchment-300 focus:outline-none focus:border-brass-500"
        >
          <option value="">All risk</option>
          <option value="Medium">Medium+</option>
          <option value="High">High+</option>
          <option value="Critical">Critical only</option>
        </select>

        <select
          value={filters.folder ?? ""}
          onChange={(e) => onChange({ ...filters, folder: e.target.value || null })}
          className="flex-1 min-w-0 bg-ink-800 border border-ink-600 rounded-sm px-1.5 py-1 text-[10px] font-mono text-parchment-300 focus:outline-none focus:border-brass-500"
        >
          <option value="">All folders</option>
          {folders.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </div>

      <p className="mt-2 text-[10px] text-parchment-600">
        Showing {visibleCount} of {nodes.length} files
      </p>
    </div>
  );
}
