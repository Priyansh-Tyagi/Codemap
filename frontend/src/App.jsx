import { useEffect, useMemo, useRef, useState } from "react";
import GraphView from "./components/GraphView";
import DetailsPanel from "./components/DetailsPanel";
import ImportsPanel from "./components/ImportsPanel";
import FileTree from "./components/FileTree";
import FilterPanel from "./components/FilterPanel";
import ImpactPanel from "./components/ImpactPanel";
import { analyzeRepository, getProjectGraph, getProjectSummary } from "./services/api";
import { emptyFilters, computeVisibleNodeIds } from "./utils/filterNodes";

export default function App() {
  const [sourceMode, setSourceMode] = useState("local"); // "local" | "github"
  const [inputValue, setInputValue] = useState("");
  const [forceRefresh, setForceRefresh] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastResultCached, setLastResultCached] = useState(false);

  const [projectId, setProjectId] = useState(null);
  const [graph, setGraph] = useState(null); // { nodes, edges }
  const [stats, setStats] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [filters, setFilters] = useState(emptyFilters());

  const graphRef = useRef(null);

  const selectedNode = useMemo(
    () => graph?.nodes.find((n) => n.id === selectedNodeId) ?? null,
    [graph, selectedNodeId]
  );

  const visibleNodeIds = useMemo(
    () => (graph ? computeVisibleNodeIds(graph.nodes, filters) : new Set()),
    [graph, filters]
  );
  const visibleNodes = useMemo(
    () => (graph ? graph.nodes.filter((n) => visibleNodeIds.has(n.id)) : []),
    [graph, visibleNodeIds]
  );
  const visibleEdges = useMemo(
    () =>
      graph
        ? graph.edges.filter((e) => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target))
        : [],
    [graph, visibleNodeIds]
  );

  // If a filter change hides the currently-selected file, clear the
  // selection rather than leaving stale details/impact panels pointing at
  // a file that's no longer visible in either the tree or the graph.
  useEffect(() => {
    if (selectedNodeId && !visibleNodeIds.has(selectedNodeId)) {
      setSelectedNodeId(null);
    }
  }, [visibleNodeIds, selectedNodeId]);

  async function handleAnalyze(e) {
    e.preventDefault();
    const value = inputValue.trim();
    if (!value) return;

    setLoading(true);
    setError(null);
    setSelectedNodeId(null);
    setFilters(emptyFilters());

    try {
      const source =
        sourceMode === "github" ? { githubUrl: value, forceRefresh } : { path: value };
      const analyzeResult = await analyzeRepository(source);
      const [graphData, summary] = await Promise.all([
        getProjectGraph(analyzeResult.projectId),
        getProjectSummary(analyzeResult.projectId),
      ]);
      setProjectId(analyzeResult.projectId);
      setGraph(graphData);
      setStats(summary);
      setLastResultCached(Boolean(analyzeResult.cached));
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(detail || "Couldn't reach the backend. Is it running on port 8000?");
      setGraph(null);
    } finally {
      setLoading(false);
    }
  }

  /** Shared by graph clicks, tree clicks, search results, and impact-list clicks. */
  function selectFile(fileId) {
    setSelectedNodeId(fileId);
    if (fileId) graphRef.current?.focusNode(fileId);
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-ink-950">
      <header className="flex items-center gap-3 px-4 h-14 border-b border-ink-700 bg-ink-900 flex-shrink-0">
        <Wordmark />

        <SourceModeToggle mode={sourceMode} onChange={setSourceMode} />

        <form onSubmit={handleAnalyze} className="flex-1 flex gap-2 max-w-xl items-center">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder={
              sourceMode === "github"
                ? "https://github.com/owner/repo"
                : "/path/to/a/local/repository"
            }
            className="flex-1 bg-ink-800 border border-ink-600 rounded-sm px-3 py-1.5 text-[13px] font-mono text-parchment-100 placeholder:text-parchment-700 focus:outline-none focus:border-brass-500"
          />
          {sourceMode === "github" && (
            <label className="flex items-center gap-1.5 text-[11px] text-parchment-400 whitespace-nowrap cursor-pointer">
              <input
                type="checkbox"
                checked={forceRefresh}
                onChange={(e) => setForceRefresh(e.target.checked)}
                className="accent-brass-500"
              />
              Force refresh
            </label>
          )}
          <button
            type="submit"
            disabled={loading}
            className="bg-brass-500 hover:bg-brass-400 disabled:opacity-40 disabled:hover:bg-brass-500 text-ink-950 text-[13px] font-medium px-4 py-1.5 rounded-sm transition-colors whitespace-nowrap"
          >
            {loading ? (sourceMode === "github" ? "Downloading…" : "Analyzing…") : "Analyze"}
          </button>
        </form>

        {!error && graph && sourceMode === "github" && (
          <span
            className={`text-[11px] font-mono whitespace-nowrap ${
              lastResultCached ? "text-brass-400" : "text-parchment-600"
            }`}
          >
            {lastResultCached ? "served from cache" : "freshly fetched"}
          </span>
        )}

        {error && (
          <span className="text-flag-400 text-[12px] font-mono truncate max-w-xs">
            {error}
          </span>
        )}
      </header>

      <main className="flex-1 flex overflow-hidden">
        <aside className="w-60 border-r border-ink-700 bg-ink-900 flex-shrink-0 flex flex-col">
          {graph ? (
            <>
              <FilterPanel
                nodes={graph.nodes}
                filters={filters}
                onChange={setFilters}
                onClear={() => setFilters(emptyFilters())}
                visibleCount={visibleNodes.length}
              />
              <div className="flex-1 overflow-y-auto">
                <FileTree
                  nodes={visibleNodes}
                  selectedNodeId={selectedNodeId}
                  onSelect={(node) => selectFile(node.id)}
                />
              </div>
            </>
          ) : (
            <p className="px-3 py-4 text-[12px] text-parchment-700">
              No project analyzed yet.
            </p>
          )}
        </aside>

        <div className="flex-1">
          {graph && graph.nodes.length === 0 ? (
            <NoFilesFoundState rootPath={inputValue} />
          ) : graph && visibleNodes.length === 0 ? (
            <FilteredEmptyState onClear={() => setFilters(emptyFilters())} />
          ) : graph ? (
            <GraphView
              ref={graphRef}
              nodes={visibleNodes}
              edges={visibleEdges}
              onNodeClick={(node) => selectFile(node?.id ?? null)}
              selectedNodeId={selectedNodeId}
            />
          ) : (
            <EmptyState />
          )}
        </div>

        <aside className="w-72 border-l border-ink-700 bg-ink-900 flex-shrink-0 overflow-y-auto">
          <DetailsPanel node={selectedNode} stats={stats} />
          <ImportsPanel node={selectedNode} edges={graph?.edges ?? []} />
          <ImpactPanel projectId={projectId} filePath={selectedNodeId} onSelectFile={selectFile} />
        </aside>
      </main>
    </div>
  );
}

function SourceModeToggle({ mode, onChange }) {
  return (
    <div className="flex items-center bg-ink-800 border border-ink-600 rounded-sm p-0.5 flex-shrink-0">
      <ToggleButton active={mode === "local"} onClick={() => onChange("local")}>
        Local path
      </ToggleButton>
      <ToggleButton active={mode === "github"} onClick={() => onChange("github")}>
        GitHub URL
      </ToggleButton>
    </div>
  );
}

function ToggleButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-2.5 py-1 text-[12px] font-mono rounded-sm transition-colors ${
        active
          ? "bg-brass-500 text-ink-950"
          : "text-parchment-400 hover:text-parchment-100"
      }`}
    >
      {children}
    </button>
  );
}

function Wordmark() {
  return (
    <div className="flex items-center gap-2 flex-shrink-0">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
        <circle cx="4" cy="15" r="2.2" fill="#c08a3f" />
        <circle cx="16" cy="5" r="2.2" fill="#7c8397" />
        <circle cx="16" cy="15" r="2.2" fill="#7c8397" />
        <path
          d="M6 14 L14 6 M14 6 L14 15 M14 15 L6 15"
          stroke="#323a4d"
          strokeWidth="1.4"
          fill="none"
        />
      </svg>
      <span className="font-display text-[15px] font-semibold text-parchment-100">
        CodeMap
      </span>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="h-full flex items-center justify-center">
      <p className="text-[13px] text-parchment-500 max-w-xs text-center leading-relaxed">
        Point CodeMap at a local repository to chart its dependencies.
      </p>
    </div>
  );
}

function FilteredEmptyState({ onClear }) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center">
        <p className="text-[13px] text-parchment-500 max-w-xs leading-relaxed">
          No files match the current filters.
        </p>
        <button
          onClick={onClear}
          className="mt-3 text-[12px] text-brass-400 hover:text-brass-300 font-mono"
        >
          Clear filters
        </button>
      </div>
    </div>
  );
}

function NoFilesFoundState({ rootPath }) {
  return (
    <div className="h-full flex items-center justify-center">
      <p className="text-[13px] text-parchment-500 max-w-sm text-center leading-relaxed">
        No JavaScript or TypeScript files found in{" "}
        <span className="font-mono text-parchment-300 break-all">{rootPath}</span>.
        <br />
        CodeMap looks for .js, .jsx, .ts, and .tsx files, skipping node_modules,
        dist, build, and similar folders.
      </p>
    </div>
  );
}
