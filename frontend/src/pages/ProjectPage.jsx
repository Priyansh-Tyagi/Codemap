import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import Wordmark from "../components/Wordmark";
import GraphView from "../components/GraphView";
import DetailsPanel from "../components/DetailsPanel";
import ImportsPanel from "../components/ImportsPanel";
import FileTree from "../components/FileTree";
import FilterPanel from "../components/FilterPanel";
import ImpactPanel from "../components/ImpactPanel";
import { getProjectGraph, getProjectSummary } from "../services/api";
import { emptyFilters, computeVisibleNodeIds } from "../utils/filterNodes";

export default function ProjectPage() {
  const { projectId } = useParams();
  const location = useLocation();
  const justAnalyzedCached = location.state?.cached;

  // "loading" | "ready" | "notfound" | "error"
  const [status, setStatus] = useState("loading");
  const [graph, setGraph] = useState(null);
  const [stats, setStats] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [filters, setFilters] = useState(emptyFilters());
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const graphRef = useRef(null);

  // The URL is the single source of truth: this runs identically whether the
  // user just analyzed something or opened someone else's shared link.
  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setGraph(null);
    setSelectedNodeId(null);
    setFilters(emptyFilters());

    Promise.all([getProjectGraph(projectId), getProjectSummary(projectId)])
      .then(([graphData, summary]) => {
        if (cancelled) return;
        setGraph(graphData);
        setStats(summary);
        setStatus("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus(err.response?.status === 404 ? "notfound" : "error");
      });

    return () => {
      cancelled = true;
    };
  }, [projectId]);

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

  useEffect(() => {
    if (selectedNodeId && !visibleNodeIds.has(selectedNodeId)) setSelectedNodeId(null);
  }, [visibleNodeIds, selectedNodeId]);

  function selectFile(fileId) {
    setSelectedNodeId(fileId);
    if (fileId) graphRef.current?.focusNode(fileId);
  }

  async function copyLink() {
    setCopyFailed(false);
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API needs a secure context and permission; fail visibly
      // rather than silently pretending it worked.
      setCopyFailed(true);
    }
  }

  if (status === "notfound") return <NotFound />;

  return (
    <div className="h-screen w-screen flex flex-col bg-ink-950">
      <header className="flex items-center gap-3 px-4 h-14 border-b border-ink-700 bg-ink-900 flex-shrink-0">
        <Wordmark />
        {stats && (
          <span className="text-[12px] font-mono text-parchment-400 truncate max-w-md">
            {stats.sourceLabel}
          </span>
        )}
        <div className="flex-1" />
        {justAnalyzedCached && status === "ready" && (
          <span className="text-[11px] font-mono text-brass-400 whitespace-nowrap">
            served from cache
          </span>
        )}
        {status === "ready" && (
          <button
            type="button"
            onClick={copyLink}
            className="border border-ink-600 hover:border-brass-500 text-parchment-200 text-[12px] font-mono px-3 py-1 rounded-sm transition-colors"
          >
            {copied ? "Copied!" : "Copy link"}
          </button>
        )}
        {copyFailed && (
          <span role="alert" className="text-flag-400 text-[11px] font-mono">
            Couldn't copy — copy the address bar instead
          </span>
        )}
        <Link to="/" className="text-[12px] font-mono text-brass-400 hover:text-brass-300">
          New analysis
        </Link>
      </header>

      <main className="flex-1 flex overflow-hidden">
        {status === "loading" && (
          <CenterMessage>Loading project…</CenterMessage>
        )}
        {status === "error" && (
          <CenterMessage>
            Couldn't reach the backend. Is it running on port 8000?
          </CenterMessage>
        )}
        {status === "ready" && (
          <>
            <aside className="w-60 border-r border-ink-700 bg-ink-900 flex-shrink-0 flex flex-col">
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
            </aside>

            <div className="flex-1">
              {graph.nodes.length === 0 ? (
                <CenterMessage>
                  No JavaScript, TypeScript, or Python files found in this project.
                </CenterMessage>
              ) : visibleNodes.length === 0 ? (
                <div className="h-full flex items-center justify-center">
                  <div className="text-center">
                    <p className="text-[13px] text-parchment-500">
                      No files match the current filters.
                    </p>
                    <button
                      onClick={() => setFilters(emptyFilters())}
                      className="mt-3 text-[12px] text-brass-400 hover:text-brass-300 font-mono"
                    >
                      Clear filters
                    </button>
                  </div>
                </div>
              ) : (
                <GraphView
                  ref={graphRef}
                  nodes={visibleNodes}
                  edges={visibleEdges}
                  onNodeClick={(node) => selectFile(node?.id ?? null)}
                  selectedNodeId={selectedNodeId}
                />
              )}
            </div>

            <aside className="w-72 border-l border-ink-700 bg-ink-900 flex-shrink-0 overflow-y-auto">
              <DetailsPanel node={selectedNode} stats={stats} />
              <ImportsPanel node={selectedNode} edges={graph.edges} />
              <ImpactPanel projectId={projectId} filePath={selectedNodeId} onSelectFile={selectFile} />
            </aside>
          </>
        )}
      </main>
    </div>
  );
}

function CenterMessage({ children }) {
  return (
    <div className="flex-1 h-full flex items-center justify-center px-4">
      <p className="text-[13px] text-parchment-500 max-w-sm text-center leading-relaxed">
        {children}
      </p>
    </div>
  );
}

function NotFound() {
  return (
    <div className="h-screen w-screen flex flex-col bg-ink-950">
      <header className="flex items-center px-4 h-14 border-b border-ink-700 bg-ink-900">
        <Wordmark />
      </header>
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <h1 className="font-display text-xl text-parchment-100">Project not found</h1>
          <p className="mt-2 text-[13px] text-parchment-500 max-w-sm">
            This link may be mistyped, or the project may no longer be stored.
          </p>
          <Link to="/" className="mt-4 inline-block text-[13px] font-mono text-brass-400 hover:text-brass-300">
            Analyze a repository
          </Link>
        </div>
      </div>
    </div>
  );
}
