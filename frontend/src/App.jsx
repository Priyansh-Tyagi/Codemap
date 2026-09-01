import { useMemo, useRef, useState } from "react";
import GraphView from "./components/GraphView";
import DetailsPanel from "./components/DetailsPanel";
import FileTree from "./components/FileTree";
import ImpactPanel from "./components/ImpactPanel";
import { analyzeRepository, getProjectGraph, getProjectSummary } from "./services/api";

export default function App() {
  const [sourceMode, setSourceMode] = useState("local"); // "local" | "github"
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [projectId, setProjectId] = useState(null);
  const [graph, setGraph] = useState(null); // { nodes, edges }
  const [stats, setStats] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState(null);

  const graphRef = useRef(null);

  const selectedNode = useMemo(
    () => graph?.nodes.find((n) => n.id === selectedNodeId) ?? null,
    [graph, selectedNodeId]
  );

  async function handleAnalyze(e) {
    e.preventDefault();
    const value = inputValue.trim();
    if (!value) return;

    setLoading(true);
    setError(null);
    setSelectedNodeId(null);

    try {
      const source = sourceMode === "github" ? { githubUrl: value } : { path: value };
      const analyzeResult = await analyzeRepository(source);
      const [graphData, summary] = await Promise.all([
        getProjectGraph(analyzeResult.projectId),
        getProjectSummary(analyzeResult.projectId),
      ]);
      setProjectId(analyzeResult.projectId);
      setGraph(graphData);
      setStats(summary);
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

        <form onSubmit={handleAnalyze} className="flex-1 flex gap-2 max-w-xl">
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
          <button
            type="submit"
            disabled={loading}
            className="bg-brass-500 hover:bg-brass-400 disabled:opacity-40 disabled:hover:bg-brass-500 text-ink-950 text-[13px] font-medium px-4 py-1.5 rounded-sm transition-colors whitespace-nowrap"
          >
            {loading ? (sourceMode === "github" ? "Downloading…" : "Analyzing…") : "Analyze"}
          </button>
        </form>

        {error && (
          <span className="text-flag-400 text-[12px] font-mono truncate max-w-xs">
            {error}
          </span>
        )}
      </header>

      <main className="flex-1 flex overflow-hidden">
        <aside className="w-60 border-r border-ink-700 bg-ink-900 flex-shrink-0">
          {graph ? (
            <FileTree
              nodes={graph.nodes}
              selectedNodeId={selectedNodeId}
              onSelect={(node) => selectFile(node.id)}
            />
          ) : (
            <p className="px-3 py-4 text-[12px] text-parchment-700">
              No project analyzed yet.
            </p>
          )}
        </aside>

        <div className="flex-1">
          {graph && graph.nodes.length > 0 ? (
            <GraphView
              ref={graphRef}
              nodes={graph.nodes}
              edges={graph.edges}
              onNodeClick={(node) => selectFile(node?.id ?? null)}
              selectedNodeId={selectedNodeId}
            />
          ) : graph ? (
            <NoFilesFoundState rootPath={inputValue} />
          ) : (
            <EmptyState />
          )}
        </div>

        <aside className="w-72 border-l border-ink-700 bg-ink-900 flex-shrink-0 overflow-y-auto">
          <DetailsPanel node={selectedNode} stats={stats} />
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
