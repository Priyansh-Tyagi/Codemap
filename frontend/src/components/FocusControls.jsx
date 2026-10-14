import { Focus } from "lucide-react";
import { MAX_HOPS, LARGE_GRAPH_THRESHOLD } from "../utils/focusNeighborhood";

/**
 * Floating control over the graph canvas for focus mode. Deliberately small:
 * one toggle, and - only while focus is on - how far out to look and an honest
 * count of what's currently drawn.
 */
export default function FocusControls({
  enabled,
  hops,
  hasSelection,
  shownCount,
  totalCount,
  onToggle,
  onHopsChange,
}) {
  const hopOptions = Array.from({ length: MAX_HOPS }, (_, i) => i + 1);

  return (
    <div className="absolute top-3 left-3 z-10 flex flex-wrap items-center gap-2 max-w-[calc(100%-1.5rem)] rounded-xl bg-surface/95 border border-line shadow-soft px-2 py-1.5">
      <button
        type="button"
        onClick={onToggle}
        aria-pressed={enabled}
        title={enabled ? "Show the whole graph" : "Show only the selected file and its neighbors"}
        className={
          "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-lg text-[12.5px] font-medium transition-colors " +
          (enabled
            ? "bg-accent text-accent-fg"
            : "text-fg-soft hover:text-fg hover:bg-surface-2 border border-line-strong")
        }
      >
        <Focus size={13} aria-hidden="true" />
        Focus
      </button>

      {enabled && (
        <>
          <div role="group" aria-label="Hops from the selected file" className="inline-flex items-center gap-1">
            {hopOptions.map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => onHopsChange(n)}
                aria-pressed={hops === n}
                title={`Include files up to ${n} import${n === 1 ? "" : "s"} away`}
                className={
                  "h-7 min-w-7 px-2 rounded-lg text-[12px] font-mono transition-colors " +
                  (hops === n
                    ? "bg-surface-2 text-fg border border-line-strong"
                    : "text-faint hover:text-fg hover:bg-surface-2")
                }
              >
                {n} hop{n === 1 ? "" : "s"}
              </button>
            ))}
          </div>

          <span className="text-[12px] text-faint px-1" aria-live="polite">
            {hasSelection ? (
              <>
                Showing {shownCount} of {totalCount} files
                {shownCount > LARGE_GRAPH_THRESHOLD && " — still large; try fewer hops or a filter"}
              </>
            ) : (
              "Select a file to focus on it"
            )}
          </span>
        </>
      )}
    </div>
  );
}
