import { useMemo } from "react";
import { ChevronDown, ListFilter } from "lucide-react";
import { colorForCategory } from "../utils/nodeColor";
import { availableCategories, availableFolders, hasActiveFilters } from "../utils/filterNodes";

const selectClass =
  "w-full appearance-none bg-surface-2 border border-line rounded-lg pl-2.5 pr-7 py-1.5 text-[12px] text-fg-soft " +
  "hover:border-line-strong focus:outline-none focus:border-fg transition-colors";

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
    <div className="p-3 border-b border-line">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-[12px] font-semibold text-fg">
          <ListFilter size={13} aria-hidden="true" />
          Filter
        </h3>
        {active && (
          <button onClick={onClear} className="text-[11px] font-medium text-muted hover:text-fg underline-offset-2 hover:underline">
            Clear
          </button>
        )}
      </div>

      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {categories.map((cat) => {
          const isActive = filters.categories.has(cat);
          const color = colorForCategory(cat);
          return (
            <button
              key={cat}
              type="button"
              aria-pressed={isActive}
              onClick={() => toggleCategory(cat)}
              className="inline-flex items-center gap-1.5 text-[11px] font-medium pl-1.5 pr-2 py-0.5 rounded-full border transition-colors"
              style={{
                borderColor: isActive ? `color-mix(in srgb, ${color} 60%, transparent)` : "var(--line)",
                background: isActive ? `color-mix(in srgb, ${color} 16%, transparent)` : "transparent",
                color: isActive ? "var(--fg)" : "var(--muted)",
              }}
            >
              <span className="w-2 h-2 rounded-full" style={{ background: color }} />
              {cat}
            </button>
          );
        })}
      </div>

      <div className="mt-2.5 grid grid-cols-2 gap-2">
        <div className="relative">
          <select
            aria-label="Minimum risk"
            value={filters.minRisk ?? ""}
            onChange={(e) => onChange({ ...filters, minRisk: e.target.value || null })}
            className={selectClass}
          >
            <option value="">All risk</option>
            <option value="Medium">Medium+</option>
            <option value="High">High+</option>
            <option value="Critical">Critical only</option>
          </select>
          <ChevronDown size={13} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-faint" aria-hidden="true" />
        </div>
        <div className="relative">
          <select
            aria-label="Folder"
            value={filters.folder ?? ""}
            onChange={(e) => onChange({ ...filters, folder: e.target.value || null })}
            className={selectClass}
          >
            <option value="">All folders</option>
            {folders.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
          <ChevronDown size={13} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-faint" aria-hidden="true" />
        </div>
      </div>

      <p className="mt-2.5 text-[11px] text-faint tabular-nums">
        Showing {visibleCount} of {nodes.length} files
      </p>
    </div>
  );
}
