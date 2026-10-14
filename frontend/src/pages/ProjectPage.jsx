import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { Check, Compass, FolderOpen, GitBranch, Link2, Loader2, Lock, Plus } from "lucide-react";
import Wordmark from "../components/Wordmark";
import AuthStatus from "../components/AuthStatus";
import ThemeToggle from "../components/ThemeToggle";
import GuidedTour from "../components/GuidedTour";
import GraphView from "../components/GraphView";
import DetailsPanel from "../components/DetailsPanel";
import ImportsPanel from "../components/ImportsPanel";
import FileTree from "../components/FileTree";
import FilterPanel from "../components/FilterPanel";
import FocusControls from "../components/FocusControls";
import ImpactPanel from "../components/ImpactPanel";
import { getProjectGraph, getProjectSummary, getProjectTour } from "../services/api";
import { describeApiError } from "../utils/apiError";
import { emptyFilters, computeVisibleNodeIds } from "../utils/filterNodes";
import { LARGE_GRAPH_THRESHOLD, neighborhoodIds, pickFocusStart } from "../utils/focusNeighborhood";

export default function ProjectPage() {
  const { projectId } = useParams();
  const location = useLocation();
  const justAnalyzedCached = location.state?.cached;

  // "loading" | "ready" | "notfound" | "error"
  const [status, setStatus] = useState("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [graph, setGraph] = useState(null);
  const [stats, setStats] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [filters, setFilters] = useState(emptyFilters());
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const [tourOpen, setTourOpen] = useState(false);
  // Focus mode: draw only the selected file's neighborhood. Large projects open in it.
  const [focus, setFocus] = useState({ enabled: false, hops: 1 });
  const graphRef = useRef(null);

  // The URL is the single source of truth: this runs identically whether the
  // user just analyzed something or opened someone else's shared link.
  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setGraph(null);
    setSelectedNodeId(null);
    setFilters(emptyFilters());
    setFocus({ enabled: false, hops: 1 });

    async function load() {
      try {
        const [graphData, summary] = await Promise.all([
          getProjectGraph(projectId),
          getProjectSummary(projectId),
        ]);
        if (cancelled) return;

        // A big graph drawn all at once is an unreadable column of tiny boxes,
        // so large projects open focused on the guided tour's first entry
        // point (deterministic, no AI). Resolved BEFORE the first render so the
        // user never sees the full hairball flash up first.
        let startId = null;
        const large = graphData.nodes.length > LARGE_GRAPH_THRESHOLD;
        if (large) {
          const ids = new Set(graphData.nodes.map((n) => n.id));
          try {
            const tour = await getProjectTour(projectId, "trace");
            for (const stop of tour.stops ?? []) {
              const candidates = [stop.fileId, ...(stop.members ?? []).map((m) => m.fileId)];
              startId = candidates.find((id) => ids.has(id)) ?? null;
              if (startId) break;
            }
          } catch {
            // tour unavailable: fall through to the local heuristic
          }
          startId ??= pickFocusStart(graphData.nodes);
          if (cancelled) return;
        }

        setGraph(graphData);
        setStats(summary);
        if (large && startId) {
          setSelectedNodeId(startId);
          setFocus({ enabled: true, hops: 1 });
        }
        setStatus("ready");
      } catch (err) {
        if (cancelled) return;
        if (err.response?.status === 404) {
          setStatus("notfound");
        } else {
          setErrorMessage(describeApiError(err));
          setStatus("error");
        }
      }
    }
    load();

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

  // Focus mode is a view over the FILTERED graph, so the two compose. The file
  // tree keeps using visibleNodes (not this) so any file stays one click away.
  const focusRootId =
    focus.enabled && selectedNodeId && visibleNodeIds.has(selectedNodeId) ? selectedNodeId : null;
  const focusIds = useMemo(
    () => (focusRootId ? neighborhoodIds(visibleEdges, focusRootId, focus.hops) : null),
    [focusRootId, visibleEdges, focus.hops]
  );
  const graphNodes = useMemo(
    () => (focusIds ? visibleNodes.filter((n) => focusIds.has(n.id)) : visibleNodes),
    [focusIds, visibleNodes]
  );
  const graphEdges = useMemo(
    () => (focusIds ? visibleEdges.filter((e) => focusIds.has(e.source) && focusIds.has(e.target)) : visibleEdges),
    [focusIds, visibleEdges]
  );
  // Remounts the canvas (which re-fits the view) whenever the focused set changes.
  const fitKey = focusRootId ? `focus:${focusRootId}:${focus.hops}` : "full";

  function selectFile(fileId) {
    setSelectedNodeId(fileId);
    // In focus mode the whole canvas re-centers on the new file instead.
    if (fileId && !focus.enabled) graphRef.current?.focusNode(fileId);
  }

  function toggleFocus() {
    if (focus.enabled) {
      setFocus((f) => ({ ...f, enabled: false }));
      return;
    }
    setFocus((f) => ({ ...f, enabled: true }));
    // Nothing selected yet: start somewhere sensible rather than do nothing.
    if (!selectedNodeId) setSelectedNodeId(pickFocusStart(visibleNodes));
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

  const ghost =
    "inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-line-strong text-[12.5px] font-medium text-fg-soft hover:text-fg hover:bg-surface-2 transition-colors";

  return (
    <div className="h-screen w-screen flex flex-col bg-page">
      <header className="h-14 px-4 flex items-center gap-3 flex-shrink-0">
        <Wordmark />
        {stats && (
          <span
            className="hidden sm:inline-flex items-center gap-1.5 h-8 px-2.5 rounded-lg bg-surface border border-line text-[12px] font-mono text-fg-soft min-w-0 max-w-md"
            title={stats.sourceLabel}
          >
            {stats.sourceType === "github" ? <GitBranch size={13} aria-hidden="true" /> : <FolderOpen size={13} aria-hidden="true" />}
            <span className="truncate">{stats.sourceLabel}</span>
          </span>
        )}
        {stats?.isPrivate && (
          <span className="inline-flex items-center gap-1 h-6 px-2 rounded-full border border-line-strong text-[11.5px] font-medium text-fg-soft">
            <Lock size={11} aria-hidden="true" />
            Private
          </span>
        )}
        <div className="flex-1" />
        {justAnalyzedCached && status === "ready" && (
          <span className="text-[12px] text-faint whitespace-nowrap">served from cache</span>
        )}
        {copyFailed && (
          <span role="alert" className="text-danger text-[12px]">
            Couldn't copy — copy the address bar instead
          </span>
        )}
        <ThemeToggle />
        {status === "ready" && (
          <button
            type="button"
            onClick={() => setTourOpen((v) => !v)}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-accent text-accent-fg text-[12.5px] font-medium hover:opacity-90 transition-opacity"
          >
            <Compass size={14} aria-hidden="true" />
            {tourOpen ? "Close tour" : "Guided tour"}
          </button>
        )}
        {status === "ready" && (
          <button type="button" onClick={copyLink} className={ghost}>
            {copied ? <Check size={14} aria-hidden="true" /> : <Link2 size={14} aria-hidden="true" />}
            {copied ? "Copied!" : "Copy link"}
          </button>
        )}
        <Link to="/" className={ghost}>
          <Plus size={14} aria-hidden="true" />
          New analysis
        </Link>
        <AuthStatus />
      </header>

      <main className="flex-1 min-h-0 flex gap-3 px-3 pb-3 relative">
        {status === "loading" && (
          <CenterMessage>
            <Loader2 size={18} className="animate-spin text-muted mb-2" aria-hidden="true" />
            Loading project…
          </CenterMessage>
        )}
        {status === "error" && <CenterMessage>{errorMessage}</CenterMessage>}
        {status === "ready" && (
          <>
            <aside className="w-64 flex-shrink-0 rounded-2xl bg-surface border border-line shadow-soft flex flex-col overflow-hidden">
              <FilterPanel
                nodes={graph.nodes}
                filters={filters}
                onChange={setFilters}
                onClear={() => setFilters(emptyFilters())}
                visibleCount={visibleNodes.length}
              />
              <div className="flex-1 min-h-0">
                <FileTree nodes={visibleNodes} selectedNodeId={selectedNodeId} onSelect={(node) => selectFile(node.id)} />
              </div>
            </aside>

            <section className="flex-1 min-w-0 rounded-2xl overflow-hidden border border-line bg-stage relative">
              {graph.nodes.length === 0 ? (
                <CenterMessage>No JavaScript, TypeScript, or Python files found in this project.</CenterMessage>
              ) : visibleNodes.length === 0 ? (
                <div className="h-full flex items-center justify-center">
                  <div className="text-center">
                    <p className="text-[13px] text-muted">No files match the current filters.</p>
                    <button
                      onClick={() => setFilters(emptyFilters())}
                      className="mt-3 text-[13px] font-medium text-fg underline underline-offset-2"
                    >
                      Clear filters
                    </button>
                  </div>
                </div>
              ) : (
                <GraphView
                  ref={graphRef}
                  nodes={graphNodes}
                  edges={graphEdges}
                  fitKey={fitKey}
                  // Clicking empty canvas clears the selection - except in focus
                  // mode, where that would throw away the file being focused on.
                  onNodeClick={(node) => (node || !focus.enabled) && selectFile(node?.id ?? null)}
                  selectedNodeId={selectedNodeId}
                />
              )}
              {visibleNodes.length > 0 && (
                <FocusControls
                  enabled={focus.enabled}
                  hops={focus.hops}
                  hasSelection={Boolean(focusRootId)}
                  shownCount={graphNodes.length}
                  totalCount={visibleNodes.length}
                  onToggle={toggleFocus}
                  onHopsChange={(hops) => setFocus((f) => ({ ...f, hops }))}
                />
              )}
            </section>

            <aside className="w-72 flex-shrink-0 rounded-2xl bg-surface border border-line shadow-soft overflow-y-auto">
              <DetailsPanel node={selectedNode} stats={stats} />
              <ImportsPanel node={selectedNode} edges={graph.edges} />
              <ImpactPanel projectId={projectId} filePath={selectedNodeId} onSelectFile={selectFile} />
            </aside>

            {tourOpen && (
              <GuidedTour projectId={projectId} onSelectFile={selectFile} onClose={() => setTourOpen(false)} />
            )}
          </>
        )}
      </main>
    </div>
  );
}

function CenterMessage({ children }) {
  return (
    <div className="flex-1 h-full flex flex-col items-center justify-center px-4 text-center">
      <div className="text-[13.5px] text-muted max-w-sm leading-relaxed flex flex-col items-center">{children}</div>
    </div>
  );
}

function NotFound() {
  return (
    <div className="h-screen w-screen flex flex-col bg-page">
      <header className="h-14 px-5 flex items-center gap-3">
        <Wordmark />
        <div className="flex-1" />
        <ThemeToggle />
      </header>
      <div className="flex-1 flex items-center justify-center px-5">
        <div className="text-center max-w-sm">
          <h1 className="text-2xl font-semibold tracking-tight text-fg">Project not found</h1>
          <p className="mt-2 text-[14px] text-muted leading-relaxed">
            This link may be mistyped, or the project may no longer be stored.
          </p>
          <Link
            to="/"
            className="mt-5 inline-flex items-center h-10 px-5 rounded-xl bg-accent text-accent-fg text-[14px] font-medium hover:opacity-90"
          >
            Analyze a repository
          </Link>
        </div>
      </div>
    </div>
  );
}
